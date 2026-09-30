"""JSON plus CSV ledgers. No numeric values are invented for unassigned tasks."""

import csv
import json
from pathlib import Path


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                    encoding='utf-8')


def _csv(path, columns, rows):
    # UTF-8 BOM permits ordinary Windows spreadsheet tools to read Chinese text.
    with Path(path).open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def export_results(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / 'plan.json', result)
    write_json(directory / 'plan-input.json', result['plan_input'])
    trips = result['trips']
    _csv(directory / 'trips.csv', [
        'trip_id', 'vehicle_id', 'type', 'speed_m_s', 'task_ids', 'route', 'valid',
        'payload_kg', 'capacity_kg', 'load_start_s', 'load_s', 'departure_s', 'depot_wait_s',
        'travel_s', 'waiting_s', 'station_unload_s', 'service_s', 'return_s', 'mission_s',
        'depot_unload_s', 'depot_unload_end_s', 'turnaround_s', 'turnaround_applied',
        'next_ready_s', 'planned_end_s', 'lateness_s', 'lateness_cost', 'distance_m',
        'transport_cost_per_s', 'transport_cost'],
        [{**t, 'task_ids': json.dumps(t['task_ids']), 'route': json.dumps(t['route'])} for t in trips])
    _csv(directory / 'stops.csv', [
        'trip_id', 'vehicle_id', 'type', 'task_id', 'station_id', 'demand_kg', 'arrival_s', 'earliest_s',
        'latest_s', 'waiting_s', 'service_start_s', 'unload_s', 'unload_end_s', 'service_s',
        'completion_s', 'lateness_s', 'lateness_cost_per_s', 'lateness_cost', 'objective_lateness_penalty',
        'remaining_payload_kg', 'status'],
        [{**stop, 'trip_id': t['trip_id'], 'vehicle_id': t['vehicle_id'], 'type': t['type']}
         for t in trips for stop in t['stops']])
    _csv(directory / 'legs.csv', ['trip_id', 'vehicle_id', 'from', 'to', 'start_s', 'end_s',
                                 'travel_s', 'distance_m'],
         [{**leg, 'trip_id': t['trip_id'], 'vehicle_id': t['vehicle_id']}
          for t in trips for leg in t['legs']])
    _csv(directory / 'unassigned.csv', ['task_id', 'reason_code', 'reason_codes', 'explanation', 'attempts_json'],
         [{**u, 'reason_codes': json.dumps(u['reason_codes']),
           'attempts_json': json.dumps(u['attempts'], ensure_ascii=False)} for u in result['unassigned']])
    all_checks = [('plan', '', c) for c in result['checks']]
    all_checks += [('trip', t['trip_id'], c) for t in trips for c in t['checks']]
    _csv(directory / 'checks.csv', ['scope', 'trip_id', 'code', 'passed', 'evidence_json'],
         [{'scope': scope, 'trip_id': trip_id, 'code': c['code'], 'passed': c['passed'],
           'evidence_json': json.dumps({k: v for k, v in c.items() if k not in ('code', 'passed')},
                                      ensure_ascii=False)} for scope, trip_id, c in all_checks])
    summary = {'profile': result['profile'], 'mode': result['mode'], 'seed': result['seed'],
               'valid': result['valid'], 'complete': result['complete'],
               'coverage': result['coverage'], **result['summary']}
    _csv(directory / 'summary.csv', list(summary), [summary])
    return directory


def export_two_stage(run, directory):
    """Both plans were freshly validated by run_two_stage before export."""
    directory = Path(directory)
    export_results(run['initial'], directory / 'initial')
    export_results(run['ga'], directory / 'ga')
    write_json(directory / 'run.json', run)
    write_json(directory / 'input-snapshot.json', run['input_snapshot'])
    write_json(directory / 'parameters.json', run['parameters'])
    write_json(directory / 'initial-population.json', run['initial_population'])
    write_json(directory / 'comparison.json', run['comparison'])
    write_json(directory / 'iterations.json', run['iterations'])
    _csv(directory / 'comparison.csv', ['metric', 'initial', 'ga', 'delta_ga_minus_initial', 'unit'],
         run['comparison']['metrics'])
    task_fields = ('status', 'vehicle_id', 'trip_id', 'arrival_s', 'waiting_s', 'service_start_s',
                   'completion_s', 'lateness_s', 'lateness_cost', 'objective_lateness_penalty', 'reason_code')
    columns = ['task_id', 'changed', *[f'{phase}_{key}' for phase in ('initial', 'ga') for key in task_fields]]
    rows = []
    for task in run['comparison']['tasks']:
        row = {'task_id': task['task_id'], 'changed': task['changed']}
        row.update({f'{phase}_{key}': task[phase].get(key) for phase in ('initial', 'ga') for key in task_fields})
        rows.append(row)
    _csv(directory / 'task-comparison.csv', columns, rows)
    rows = []
    for iteration in run['iterations']:
        row = {k: v for k, v in iteration.items() if k not in ('generation_best', 'best_known')}
        row['best_chromosome'] = json.dumps(row['best_chromosome'])
        row.update({f'{label}_{key}': value for label in ('generation_best', 'best_known')
                    for key, value in iteration[label].items() if key != 'cost_unit'})
        rows.append(row)
    _csv(directory / 'iterations.csv', list(rows[0]), rows)
    return directory
