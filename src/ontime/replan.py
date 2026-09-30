"""2026 extension: simulated depot-checkpoint replanning, never execution approval."""

from dataclasses import replace

from .evaluate import check_plan, parse_plan
from .export import _csv, export_results, export_two_stage, write_json
from .ga import run_two_stage
from .input import InputError, as_problem, problem_to_dict
from .models import Plan


def time_segments(trip):
    """Disjoint activity intervals from the independently recalculated trip ledger."""
    rows = []
    def add(kind, start, end, task_id=None):
        if end > start:
            rows.append({'kind': kind, 'start_s': start, 'end_s': end, 'task_id': task_id})
    add('depot_load', trip['load_start_s'], trip['departure_s'])
    for leg in trip['legs']:
        add('travel', leg['start_s'], leg['end_s'])
    for stop in trip['stops']:
        add('wait', stop['arrival_s'], stop['service_start_s'], stop['task_id'])
        add('station_unload', stop['service_start_s'], stop['unload_end_s'], stop['task_id'])
        add('service', stop['unload_end_s'], stop['completion_s'], stop['task_id'])
    add('depot_unload', trip['return_s'], trip['depot_unload_end_s'])
    if trip['turnaround_applied']:
        add('turnaround', trip['depot_unload_end_s'], trip['next_ready_s'])
    return sorted(rows, key=lambda row: (row['start_s'], row['end_s']))


def prepare_checkpoint(problem, baseline, checkpoint_s, unavailable_vehicle_id):
    problem = as_problem(problem)
    if type(checkpoint_s) is not int or checkpoint_s < 0:
        raise InputError('checkpoint_s: expected nonnegative integer seconds')
    if unavailable_vehicle_id not in {v.id for v in problem.vehicles}:
        raise InputError('unavailable_vehicle_id: unknown device')
    evaluated = check_plan(problem, baseline)
    if not evaluated.valid:
        raise InputError('Replanning requires an independently valid baseline plan')
    ledger = evaluated.to_dict()
    # Events at exactly load_start occur before loading: such trips are adjustable.
    frozen = tuple(t for t in baseline.trips if t.load_start_s < checkpoint_s)
    frozen_ids = {t.trip_id for t in frozen}
    fixed_tasks = {tid for t in frozen for tid in t.task_ids}
    completed, segments, ready = [], [], {}
    for trip in ledger['trips']:
        if trip['trip_id'] not in frozen_ids:
            continue
        if (trip['vehicle_id'] == unavailable_vehicle_id and
                trip['depot_unload_end_s'] > checkpoint_s):
            raise InputError('Active-device failure is unsupported; checkpoint failure must occur at depot after unloading')
        ready[trip['vehicle_id']] = max(ready.get(trip['vehicle_id'], 0), trip['next_ready_s'])
        completed.extend(s['task_id'] for s in trip['stops'] if s['completion_s'] <= checkpoint_s)
        for segment in time_segments(trip):
            segments.append({**segment, 'trip_id': trip['trip_id'], 'vehicle_id': trip['vehicle_id'],
                             'executed_until_s': (min(checkpoint_s, segment['end_s'])
                                                  if segment['start_s'] < checkpoint_s else None),
                             'executed_s': max(0, min(checkpoint_s, segment['end_s']) - segment['start_s']),
                             'commitment': 'frozen', 'telemetry_source': 'simulated baseline clock'})
    adjustable = tuple(t for t in problem.tasks if t.id not in fixed_tasks)
    vehicles = []
    for vehicle in problem.vehicles:
        start = max(checkpoint_s, vehicle.available_from_s, ready.get(vehicle.id, 0))
        available = vehicle.available and vehicle.id != unavailable_vehicle_id and start <= vehicle.available_until_s
        # Closed shifts are explicitly unavailable. Keep a valid zero-width input interval.
        vehicles.append(replace(vehicle, available=available,
                                available_from_s=min(start, vehicle.available_until_s)))
    residual = replace(problem, tasks=adjustable, vehicles=tuple(vehicles),
                       scenario_label=problem.scenario_label + ' / checkpoint residual',
                       metadata={**problem.metadata, 'extension': 'depot_checkpoint_replan_2026_v1',
                                 'checkpoint_s': checkpoint_s, 'unavailable_vehicle_id': unavailable_vehicle_id})
    residual = as_problem(residual)
    return {'problem': problem, 'baseline': ledger, 'frozen': frozen, 'residual': residual,
            'completed_task_ids': sorted(completed),
            'locked_unfinished_task_ids': sorted(fixed_tasks - set(completed)),
            'adjustable_task_ids': [t.id for t in adjustable], 'frozen_segments': segments}


def validate_replanning(problem, baseline, candidate, checkpoint_s, unavailable_vehicle_id):
    """Independent candidate gate: reconstruct history, then recheck all future trips."""
    context = prepare_checkpoint(problem, baseline, checkpoint_s, unavailable_vehicle_id)
    expected = {t.trip_id: t for t in context['frozen']}
    actual = {t.trip_id: t for t in candidate.trips if t.trip_id in expected}
    future = tuple(t for t in candidate.trips if t.trip_id not in expected)
    residual_plan = Plan(future, candidate.unassigned, candidate.mode, candidate.seed)
    residual = check_plan(context['residual'], residual_plan)
    combined = check_plan(context['problem'], candidate)
    checks = [
        {'code': 'frozen_trip_records_unchanged', 'passed': actual == expected},
        {'code': 'mode_unchanged', 'passed': candidate.mode == baseline.mode},
        {'code': 'new_loads_after_checkpoint', 'passed': all(t.load_start_s >= checkpoint_s for t in future)},
        {'code': 'failed_vehicle_has_no_new_trips', 'passed': all(t.vehicle_id != unavailable_vehicle_id for t in future)},
        {'code': 'residual_independent_validation', 'passed': residual.valid},
        {'code': 'combined_historical_physical_validation', 'passed': combined.valid},
    ]
    # The static original availability applies to history only; residual input enforces the failure from the event.
    return {'valid': all(c['passed'] for c in checks), 'checks': checks,
            'residual_evaluation': residual.to_dict(), 'combined_evaluation': combined.to_dict()}


def replan_at_checkpoint(problem, baseline, checkpoint_s, unavailable_vehicle_id, parameters=None, costs=None):
    context = prepare_checkpoint(problem, baseline, checkpoint_s, unavailable_vehicle_id)
    run = run_two_stage(context['residual'], baseline.mode, parameters, costs)
    future = parse_plan(context['residual'], run['ga']['plan_input'], baseline.mode, run['parameters']['seed'])
    reserved = {t.trip_id for t in baseline.trips}
    new_trips = []
    for index, trip in enumerate(future.trips, 1):
        name = f'replan-{index:03d}'
        while name in reserved:
            name = 'new-' + name
        reserved.add(name)
        new_trips.append(replace(trip, trip_id=name))
    candidate = Plan(tuple(sorted((*context['frozen'], *new_trips),
                                 key=lambda t: (t.vehicle_id, t.load_start_s, t.trip_id))),
                     future.unassigned, baseline.mode, future.seed)
    checked = validate_replanning(problem, baseline, candidate, checkpoint_s, unavailable_vehicle_id)
    if not checked['valid']:
        raise RuntimeError('Replanning candidate failed independent history/future validation')
    combined = checked['combined_evaluation']
    combined['checks'].extend(checked['checks'])
    combined.update(approval_status='not_approved', requires_human_approval=True,
                    execution_started=False, execution_status='candidate_only',
                    availability_semantics='original availability for history; temporal failure gate for future')
    completed = set(context['completed_task_ids'])
    locked = set(context['locked_unfinished_task_ids'])
    for trip in combined['trips']:
        for stop in trip['stops']:
            stop['status'] = ('simulated_completed' if stop['task_id'] in completed else
                              'locked_unfinished' if stop['task_id'] in locked else 'candidate_not_approved')
    before_stops = {s['task_id']: (t, s) for t in context['baseline']['trips'] for s in t['stops']}
    after_stops = {s['task_id']: (t, s) for t in combined['trips'] for s in t['stops']}
    omissions = {u['task_id']: u for u in combined['unassigned']}
    task_states = []
    for task in context['problem'].tasks:
        before_trip, _ = before_stops.get(task.id, ({}, {}))
        after_trip, stop = after_stops.get(task.id, ({}, {}))
        task_states.append({'task_id': task.id, 'station_id': task.station_id,
                            'state': stop.get('status', 'unassigned'),
                            'baseline_vehicle_id': before_trip.get('vehicle_id'),
                            'candidate_vehicle_id': after_trip.get('vehicle_id'),
                            'trip_id': after_trip.get('trip_id'),
                            'service_start_s': stop.get('service_start_s'),
                            'completion_s': stop.get('completion_s'), 'lateness_s': stop.get('lateness_s'),
                            'reason_code': omissions.get(task.id, {}).get('reason_code'),
                            'approval_status': 'not_approved'})
    return {'extension_profile': 'depot_checkpoint_replan_2026_v1', 'introduced_in': 2026,
            'illustrative': True, 'checkpoint_s': checkpoint_s, 'unavailable_vehicle_id': unavailable_vehicle_id,
            'event_source': 'simulated depot event; no hardware telemetry',
            'approval_status': 'not_approved', 'requires_human_approval': True, 'execution_started': False,
            'completed_task_ids': context['completed_task_ids'],
            'locked_unfinished_task_ids': context['locked_unfinished_task_ids'],
            'adjustable_task_ids': context['adjustable_task_ids'],
            'frozen_trip_ids': [t.trip_id for t in context['frozen']],
            'frozen_segments': context['frozen_segments'],
            'baseline_plan_input': baseline.to_dict(), 'task_states': task_states,
            'residual_input': problem_to_dict(context['residual']), 'residual_run': run,
            'validation': checked, 'combined': combined}


def export_replanning(result, directory):
    from pathlib import Path
    directory = Path(directory)
    export_two_stage(result['residual_run'], directory / 'residual')
    export_results(result['combined'], directory / 'combined')
    write_json(directory / 'residual-input.json', result['residual_input'])
    write_json(directory / 'replan.json', result)
    _csv(directory / 'task-state.csv', ['task_id', 'station_id', 'state', 'baseline_vehicle_id',
                                       'candidate_vehicle_id', 'trip_id', 'service_start_s',
                                       'completion_s', 'lateness_s', 'reason_code', 'approval_status'],
         result['task_states'])
    return directory
