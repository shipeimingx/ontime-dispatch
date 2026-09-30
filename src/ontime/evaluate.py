"""Independent plan validation: recompute input routes, never call the heuristic."""

from collections import Counter
from fractions import Fraction
import math

from .input import InputError, as_problem, fields, identifier, seconds
from .models import (CandidateAttempt, Check, Evaluation, Plan, ScheduledStop, Trip,
                     TripEvaluation, UnassignedTask, Vehicle, TravelLeg)


def check_trip(problem, vehicle, trip, mode, ready_s=None):
    if mode not in ('soft', 'hard'):
        raise InputError('mode: expected soft or hard')
    tasks = {task.id: task for task in problem.tasks}
    selected = [tasks[key] for key in trip.task_ids]
    payload = sum((Fraction(str(t.demand_kg)) for t in selected), Fraction(0))
    minimum_start = max(vehicle.available_from_s,
                        vehicle.available_from_s if ready_s is None else ready_s)
    result = TripEvaluation(
        trip=trip, vehicle_type=vehicle.type, speed_m_s=vehicle.speed_m_s,
        route=(problem.depot_id, *(t.station_id for t in selected), problem.depot_id),
        payload_kg=float(payload), capacity_kg=vehicle.capacity_kg,
        departure_s=trip.load_start_s + vehicle.load_s,
        depot_wait_s=max(0, trip.load_start_s - minimum_start), load_s=vehicle.load_s,
        depot_unload_s=vehicle.depot_unload_s, turnaround_s=vehicle.turnaround_s)

    def check(code, passed, **evidence):
        result.checks.append(Check(code, bool(passed), evidence))

    check('nonempty_trip', bool(selected))
    check('vehicle_available', vehicle.available)
    check('unique_tasks_in_trip', len(set(trip.task_ids)) == len(trip.task_ids))
    check('payload', payload <= Fraction(str(vehicle.capacity_kg)),
          payload_kg=result.payload_kg, capacity_kg=vehicle.capacity_kg)
    for task in selected:
        compatible = vehicle.type in task.eligible_types and (
            task.eligible_vehicle_ids is None or vehicle.id in task.eligible_vehicle_ids)
        check('eligibility', compatible, task_id=task.id, vehicle_id=vehicle.id)
    check('load_start', trip.load_start_s >= minimum_start,
          load_start_s=trip.load_start_s, required_ready_s=minimum_start)
    travel = problem.travel_time_s[vehicle.type]
    distances = problem.distance_m[vehicle.type] if problem.distance_m else None
    node, clock, remaining = problem.depot_id, result.departure_s, payload

    def leg(target):
        nonlocal node, clock
        duration = travel[node][target]
        check('route_edge', duration is not None, from_node=node, to_node=target)
        if duration is None:
            return False
        result.legs.append(TravelLeg(node, target, clock, clock + duration, duration,
                                     distances[node][target] if distances else None))
        clock += duration
        node = target
        return True

    for task in selected:
        if not leg(task.station_id):
            break
        arrival = clock
        begin = max(arrival, task.earliest_s)
        unload_end = begin + task.unload_s
        finish = unload_end + task.service_s
        late = max(0, begin - task.latest_s)
        check('time_window', mode == 'soft' or late == 0, task_id=task.id,
              mode=mode, service_start_s=begin, latest_s=task.latest_s, lateness_s=late)
        cost = late * task.lateness_cost_per_s
        if not math.isfinite(cost):
            raise InputError('lateness cost exceeds finite numeric output range')
        remaining -= Fraction(str(task.demand_kg))
        result.stops.append(ScheduledStop(
            task_id=task.id, station_id=task.station_id, arrival_s=arrival,
            earliest_s=task.earliest_s, latest_s=task.latest_s, waiting_s=begin - arrival,
            service_start_s=begin, unload_s=task.unload_s, unload_end_s=unload_end,
            service_s=task.service_s, completion_s=finish, lateness_s=late,
            lateness_cost_per_s=task.lateness_cost_per_s, lateness_cost=cost,
            remaining_payload_kg=float(remaining), demand_kg=task.demand_kg))
        clock = finish
    else:
        if leg(problem.depot_id):
            result.return_s = clock
            result.mission_s = clock - result.departure_s
            result.depot_unload_end_s = clock + vehicle.depot_unload_s
            result.next_ready_s = result.depot_unload_end_s + vehicle.turnaround_s
            check('trip_limit', result.mission_s <= vehicle.trip_limit_s,
                  mission_s=result.mission_s, trip_limit_s=vehicle.trip_limit_s)
            check('availability_end', result.depot_unload_end_s <= vehicle.available_until_s,
                  depot_unload_end_s=result.depot_unload_end_s,
                  available_until_s=vehicle.available_until_s)
    return result


def _unassigned(item):
    fields(item, ('task_id', 'reason_code', 'explanation'), ('reason_codes', 'attempts'), 'unassigned')
    for key in ('task_id', 'reason_code', 'explanation'):
        identifier(item[key], f'unassigned.{key}')
    reasons = item.get('reason_codes', [])
    if not isinstance(reasons, list) or any(not isinstance(x, str) for x in reasons):
        raise InputError('unassigned.reason_codes: expected string array')
    attempts = []
    if not isinstance(item.get('attempts', []), list):
        raise InputError('unassigned.attempts: expected array')
    for attempt in item.get('attempts', []):
        fields(attempt, ('vehicle_id', 'candidate_kind', 'candidate_task_ids', 'failed_checks'),
               ('insertion_position',), 'unassigned.attempt')
        for key in ('vehicle_id', 'candidate_kind'):
            identifier(attempt[key], f'attempt.{key}')
        if not isinstance(attempt['candidate_task_ids'], list):
            raise InputError('attempt.candidate_task_ids: expected array')
        for key in attempt['candidate_task_ids']:
            identifier(key, 'attempt.candidate_task_ids')
        position = attempt.get('insertion_position')
        if position is not None:
            seconds(position, 'attempt.insertion_position')
        if not isinstance(attempt['failed_checks'], list):
            raise InputError('attempt.failed_checks: expected array')
        checks = []
        for check in attempt['failed_checks']:
            if (not isinstance(check, dict) or not isinstance(check.get('code'), str)
                    or type(check.get('passed')) is not bool):
                raise InputError('attempt.failed_checks: expected code/boolean passed')
            checks.append(Check(check['code'], check['passed'],
                                {k: v for k, v in check.items() if k not in ('code', 'passed')}))
        attempts.append(CandidateAttempt(attempt['vehicle_id'], attempt['candidate_kind'],
                                          tuple(attempt['candidate_task_ids']), tuple(checks), position))
    return UnassignedTask(item['task_id'], item['reason_code'], item['explanation'],
                          tuple(reasons), tuple(attempts))


def parse_plan(problem, value, mode=None, seed=0):
    """Legacy trip-only plans get an explicit unassigned record for each omission."""
    fields(value, ('trips',), ('unassigned',), 'plan')
    if not isinstance(value['trips'], list):
        raise InputError('plan.trips: expected array')
    vehicles = {v.id for v in problem.vehicles}
    task_ids = {t.id for t in problem.tasks}
    trips = []
    for item in value['trips']:
        fields(item, ('trip_id', 'vehicle_id', 'task_ids', 'load_start_s'), (), 'plan.trip')
        identifier(item['trip_id'], 'plan.trip.trip_id')
        identifier(item['vehicle_id'], 'plan.trip.vehicle_id')
        if item['vehicle_id'] not in vehicles:
            raise InputError('plan.trip.vehicle_id: unknown vehicle')
        if not isinstance(item['task_ids'], list) or not item['task_ids']:
            raise InputError('plan.trip.task_ids: expected nonempty array')
        for task_id in item['task_ids']:
            identifier(task_id, 'plan.trip.task_ids')
            if task_id not in task_ids:
                raise InputError(f'plan.trip.task_ids: unknown task {task_id}')
        seconds(item['load_start_s'], 'plan.trip.load_start_s')
        trips.append(Trip(item['trip_id'], item['vehicle_id'], tuple(item['task_ids']), item['load_start_s']))
    if 'unassigned' not in value:
        assigned = {key for t in trips for key in t.task_ids}
        unassigned = [UnassignedTask(key, 'not_in_plan', 'Explicitly unplanned in supplied trip-only JSON.')
                      for key in sorted(task_ids - assigned)]
    else:
        if not isinstance(value['unassigned'], list):
            raise InputError('plan.unassigned: expected array')
        unassigned = [_unassigned(item) for item in value['unassigned']]
        if any(u.task_id not in task_ids for u in unassigned):
            raise InputError('unassigned.task_id: unknown task')
    return Plan(tuple(trips), tuple(unassigned), mode or problem.window_mode, seed)


def check_plan(problem, plan):
    """Recompute times; check uniqueness, complete accounting and per-device timeline."""
    problem = as_problem(problem)
    if plan.mode not in ('soft', 'hard'):
        raise InputError('mode: expected soft or hard')
    if type(plan.seed) is not int:
        raise InputError('seed: expected integer')
    plan = parse_plan(problem, plan.to_dict(), plan.mode, plan.seed)
    vehicles = {v.id: v for v in problem.vehicles}
    ready = {v.id: v.available_from_s for v in problem.vehicles}
    trips, checks, seen = [], [], Counter()
    for trip in plan.trips:
        evaluated = check_trip(problem, vehicles[trip.vehicle_id], trip, plan.mode, ready[trip.vehicle_id])
        trips.append(evaluated)
        seen.update(trip.task_ids)
        if evaluated.next_ready_s is not None:
            ready[trip.vehicle_id] = max(ready[trip.vehicle_id], evaluated.next_ready_s)
        else:
            checks.append(Check('incomplete_trip_timeline', False, {'trip_id': trip.trip_id}))
    ids = [t.trip_id for t in plan.trips]
    checks.append(Check('unique_trip_ids', len(ids) == len(set(ids))))
    duplicates = sorted(key for key, count in seen.items() if count > 1)
    checks.append(Check('unique_tasks_across_trips', not duplicates, {'duplicate_task_ids': duplicates}))
    omitted = Counter(u.task_id for u in plan.unassigned)
    duplicates = sorted(key for key, count in omitted.items() if count > 1)
    checks.append(Check('unique_unassigned_tasks', not duplicates, {'duplicate_task_ids': duplicates}))
    overlap = sorted(seen.keys() & omitted.keys())
    checks.append(Check('assigned_unassigned_disjoint', not overlap, {'task_ids': overlap}))
    missing = sorted({t.id for t in problem.tasks} - seen.keys() - omitted.keys())
    checks.append(Check('all_tasks_accounted_for', not missing, {'missing_task_ids': missing}))
    last = {t.trip.vehicle_id: index for index, t in enumerate(trips)}
    for index, trip in enumerate(trips):
        trip.turnaround_applied = index != last[trip.trip.vehicle_id]
    return Evaluation(plan, trips, checks)


def evaluate_trip(problem, vehicle, task_ids, load_start_s, mode, ready_s=None):
    """Dictionary adapter retained for v1 clients; typed core uses check_trip."""
    problem = as_problem(problem)
    vehicle = vehicle if isinstance(vehicle, Vehicle) else Vehicle(**vehicle)
    canonical = next((v for v in problem.vehicles if v.id == vehicle.id), None)
    if canonical is None or vehicle != canonical:
        raise InputError('vehicle: must match the validated problem device; capacity/availability overrides are forbidden')
    spec = {'trips': [{'trip_id': 'candidate', 'vehicle_id': vehicle.id,
                      'task_ids': list(task_ids), 'load_start_s': load_start_s}]}
    parsed = parse_plan(problem, spec, mode)
    return check_trip(problem, canonical, parsed.trips[0], mode, ready_s).to_dict()


def evaluate_plan(problem, plan, mode=None):
    problem = as_problem(problem)
    if isinstance(plan, Plan):
        if mode is not None:
            from dataclasses import replace
            plan = replace(plan, mode=mode)
    else:
        plan = parse_plan(problem, plan, mode)
    return check_plan(problem, plan).to_dict()
