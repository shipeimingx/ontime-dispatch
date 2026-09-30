"""Boundary checks for the 2026 model; these are not performance experiments."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ontime.evaluate import evaluate_plan, evaluate_trip
from ontime.input import InputError, load_problem, read_json, validate_problem
from ontime.scheduler import schedule


def example():
    return {
        'schema_version': 1, 'scenario_label': 'Illustrative test data',
        'depot_id': 'D', 'stations': ['A', 'B'],
        'vehicles': [{'id': 'U1', 'type': 'UAV', 'available': True, 'capacity_kg': 4,
                      'trip_limit_s': 1000, 'available_from_s': 0, 'available_until_s': 500,
                      'load_s': 10, 'depot_unload_s': 10, 'turnaround_s': 20}],
        'tasks': [{'id': 'T1', 'station_id': 'A', 'demand_kg': 2, 'earliest_s': 0,
                   'latest_s': 500, 'unload_s': 2, 'service_s': 3, 'eligible_types': ['UAV']},
                  {'id': 'T2', 'station_id': 'B', 'demand_kg': 2, 'earliest_s': 0,
                   'latest_s': 500, 'unload_s': 2, 'service_s': 3, 'eligible_types': ['UAV']}],
        'travel_time_s': {
            'UAV': {'D': {'D': 0, 'A': 10, 'B': 20}, 'A': {'D': 15, 'A': 0, 'B': 5},
                    'B': {'D': 25, 'A': 7, 'B': 0}},
            'AGV': {'D': {'D': 0, 'A': 100, 'B': 200}, 'A': {'D': 150, 'A': 0, 'B': 50},
                    'B': {'D': 250, 'A': 70, 'B': 0}},
        },
    }


def trip(problem, task_ids=('T1',), start=0, mode='soft'):
    return evaluate_trip(problem, problem['vehicles'][0], list(task_ids), start, mode)


def failed(result):
    return {check['code'] for check in result['checks'] if not check['passed']}


class TimingTests(unittest.TestCase):
    def test_full_multistop_ledger(self):
        result = trip(example(), ('T1', 'T2'))
        self.assertTrue(result['valid'])
        self.assertEqual(result['payload_kg'], 4)
        self.assertEqual(result['departure_s'], 10)
        self.assertEqual([s['arrival_s'] for s in result['stops']], [20, 30])
        self.assertEqual([s['completion_s'] for s in result['stops']], [25, 35])
        self.assertEqual([s['remaining_payload_kg'] for s in result['stops']], [2, 0])
        self.assertEqual(result['return_s'], 60)
        self.assertEqual(result['mission_s'], 50)
        self.assertEqual(result['depot_unload_end_s'], 70)
        self.assertEqual(result['next_ready_s'], 90)
        self.assertEqual(result['mission_s'], result['travel_s'] + result['waiting_s']
                         + result['station_unload_s'] + result['service_s'])

    def test_whole_trip_load_not_each_task(self):
        problem = example()
        problem['vehicles'][0]['capacity_kg'] = 3
        self.assertTrue(trip(problem, ('T1',))['valid'])
        self.assertTrue(trip(problem, ('T2',))['valid'])
        self.assertIn('payload', failed(trip(problem, ('T1', 'T2'))))
        planned = schedule(problem)
        self.assertTrue(planned['complete'])
        self.assertEqual(len(planned['trips']), 2)

    def test_decimal_payload_exact_boundary(self):
        problem = example()
        problem['vehicles'][0]['capacity_kg'] = 0.3
        problem['tasks'][0]['demand_kg'] = 0.1
        problem['tasks'][1]['demand_kg'] = 0.2
        self.assertTrue(trip(problem, ('T1', 'T2'))['valid'])

    def test_waiting_counts_toward_endurance(self):
        problem = example()
        problem['tasks'][0]['earliest_s'] = 100
        problem['vehicles'][0]['trip_limit_s'] = 109
        result = trip(problem)
        self.assertEqual(result['stops'][0]['waiting_s'], 80)
        self.assertEqual(result['mission_s'], 110)
        self.assertIn('trip_limit', failed(result))
        problem['vehicles'][0]['trip_limit_s'] = 110
        self.assertTrue(trip(problem)['valid'])

    def test_return_is_required_by_endurance(self):
        problem = example()
        problem['vehicles'][0]['trip_limit_s'] = 29
        result = trip(problem)
        self.assertEqual(result['mission_s'], 30)
        self.assertIn('trip_limit', failed(result))

    def test_warehouse_load_and_unload_in_shift(self):
        problem = example()
        problem['vehicles'][0]['available_until_s'] = 49
        self.assertIn('availability_end', failed(trip(problem)))
        problem['vehicles'][0]['available_until_s'] = 50
        self.assertTrue(trip(problem)['valid'])

    def test_multitrip_turnaround_not_final_shift_requirement(self):
        problem = example()
        problem['vehicles'][0].update(capacity_kg=2, available_until_s=140)
        result = schedule(problem)
        first, second = result['trips']
        self.assertTrue(result['complete'])
        self.assertEqual(first['next_ready_s'], 70)
        self.assertEqual(second['load_start_s'], 70)
        self.assertEqual(second['departure_s'], 80)
        self.assertEqual(second['depot_unload_end_s'], 140)
        self.assertEqual(second['next_ready_s'], 160)
        self.assertTrue(first['turnaround_applied'])
        self.assertFalse(second['turnaround_applied'])
        self.assertEqual(second['planned_end_s'], 140)
        problem['vehicles'][0]['available_until_s'] = 139
        self.assertFalse(schedule(problem)['complete'])

    def test_window_on_service_start_not_completion(self):
        problem = example()
        problem['tasks'][0].update(earliest_s=20, latest_s=20)
        result = trip(problem, mode='hard')
        self.assertTrue(result['valid'])
        self.assertEqual(result['stops'][0]['completion_s'], 25)
        self.assertEqual(result['stops'][0]['lateness_s'], 0)

    def test_soft_default_and_hard_lateness(self):
        problem = example()
        problem['tasks'] = [problem['tasks'][0]]
        problem['tasks'][0]['latest_s'] = 19
        result = schedule(problem)
        self.assertEqual(result['mode'], 'soft')
        self.assertTrue(result['complete'])
        self.assertEqual(result['summary']['lateness_s'], 1)
        hard = schedule(problem, 'hard')
        self.assertFalse(hard['complete'])
        self.assertEqual(hard['coverage'], 'No assignment')
        self.assertEqual(hard['unassigned_task_ids'], ['T1'])
        self.assertFalse(hard['search_exhaustive'])
        self.assertEqual(hard['unassigned'][0]['attempts'][0]['failed_checks'][0]['code'], 'time_window')

    def test_type_specific_asymmetric_travel(self):
        problem = example()
        problem['vehicles'][0]['type'] = 'AGV'
        problem['tasks'][0]['eligible_types'] = ['AGV']
        result = trip(problem)
        self.assertTrue(result['valid'])
        self.assertEqual([leg['travel_s'] for leg in result['legs']], [100, 150])
        self.assertEqual(result['mission_s'], 255)

    def test_parallel_heterogeneous_devices(self):
        problem = example()
        agv = {**problem['vehicles'][0], 'id': 'G1', 'type': 'AGV'}
        problem['vehicles'].append(agv)
        problem['tasks'][1]['eligible_types'] = ['AGV']
        result = schedule(problem)
        self.assertTrue(result['complete'])
        self.assertEqual({t['vehicle_id'] for t in result['trips']}, {'U1', 'G1'})
        self.assertEqual([t['load_start_s'] for t in result['trips']], [0, 0])
        self.assertEqual([t['departure_s'] for t in result['trips']], [10, 10])

    def test_unavailable_or_ineligible_is_hard_in_soft(self):
        problem = example()
        problem['vehicles'][0]['available'] = False
        self.assertIn('vehicle_available', failed(trip(problem)))
        problem['vehicles'][0]['available'] = True
        problem['tasks'][0]['eligible_types'] = ['AGV']
        self.assertIn('eligibility', failed(trip(problem)))

    def test_id_eligibility_intersects_type(self):
        problem = example()
        problem['vehicles'].append({**problem['vehicles'][0], 'id': 'U2'})
        problem['tasks'][0]['eligible_vehicle_ids'] = ['U2']
        self.assertIn('eligibility', failed(trip(problem)))
        validate_problem(problem)

    def test_forbidden_return_does_not_invent_eta(self):
        problem = example()
        problem['travel_time_s']['UAV']['A']['D'] = None
        result = trip(problem)
        self.assertFalse(result['valid'])
        self.assertIsNone(result['return_s'])
        self.assertIsNone(result['next_ready_s'])
        self.assertIn('route_edge', failed(result))

    def test_availability_start_and_depot_wait(self):
        problem = example()
        problem['vehicles'][0]['available_from_s'] = 30
        self.assertIn('load_start', failed(trip(problem)))
        result = trip(problem, start=40)
        self.assertTrue(result['valid'])
        self.assertEqual(result['depot_wait_s'], 10)
        self.assertEqual(result['mission_s'], 30)


class PlanTests(unittest.TestCase):
    def test_overlap_rejected(self):
        plan = {'trips': [
            {'trip_id': '1', 'vehicle_id': 'U1', 'task_ids': ['T1'], 'load_start_s': 0},
            {'trip_id': '2', 'vehicle_id': 'U1', 'task_ids': ['T2'], 'load_start_s': 69},
        ]}
        result = evaluate_plan(example(), plan)
        self.assertFalse(result['valid'])
        self.assertIn('load_start', failed(result['trips'][1]))

    def test_duplicate_task_across_trips_rejected(self):
        plan = {'trips': [
            {'trip_id': '1', 'vehicle_id': 'U1', 'task_ids': ['T1'], 'load_start_s': 0},
            {'trip_id': '2', 'vehicle_id': 'U1', 'task_ids': ['T1'], 'load_start_s': 70},
        ]}
        result = evaluate_plan(example(), plan)
        self.assertFalse(result['valid'])
        self.assertIn('unique_tasks_across_trips', failed(result))
        self.assertEqual(result['unassigned_task_ids'], ['T2'])

    def test_duplicate_in_trip_is_not_split_delivery(self):
        plan = {'trips': [{'trip_id': '1', 'vehicle_id': 'U1',
                           'task_ids': ['T1', 'T1'], 'load_start_s': 0}]}
        result = evaluate_plan(example(), plan)
        self.assertFalse(result['valid'])
        self.assertIn('unique_tasks_in_trip', failed(result['trips'][0]))

    def test_partial_is_valid_but_not_complete(self):
        plan = {'trips': [{'trip_id': '1', 'vehicle_id': 'U1',
                           'task_ids': ['T1'], 'load_start_s': 0}]}
        result = evaluate_plan(example(), plan)
        self.assertTrue(result['valid'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['coverage'], 'Partial')
        self.assertEqual(result['execution_status'], 'candidate_only')

    def test_empty_tasks_and_no_devices_terminate(self):
        problem = example()
        problem['vehicles'] = []
        result = schedule(validate_problem(problem))
        self.assertTrue(result['valid'])
        self.assertEqual(result['summary']['unassigned_count'], 2)
        problem['tasks'] = []
        self.assertTrue(schedule(validate_problem(problem))['complete'])

    def test_schedule_deterministic_and_does_not_mutate_input(self):
        problem = example()
        before = copy.deepcopy(problem)
        self.assertEqual(schedule(problem), schedule(problem))
        self.assertEqual(problem, before)

    def test_oversized_task_preserved_with_evidence(self):
        problem = example()
        problem['tasks'][0]['demand_kg'] = 999
        result = schedule(validate_problem(problem))
        self.assertEqual(result['assigned_task_ids'], ['T2'])
        self.assertEqual(result['unassigned_task_ids'], ['T1'])
        self.assertIn('payload', {c['code'] for c in result['unassigned'][0]['attempts'][0]['failed_checks']})


class InputTests(unittest.TestCase):
    def test_bad_units_unknown_fields_and_numeric_values(self):
        changes = [('battery_percent', 50), ('trip_limit_min', 30),
                   ('load_s', 0.5), ('load_s', True), ('load_s', -1),
                   ('capacity_kg', float('nan')), ('trip_limit_s', 0)]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                problem = example()
                problem['vehicles'][0][field] = value
                with self.assertRaises(InputError):
                    validate_problem(problem)

    def test_matrix_window_and_duplicate_ids(self):
        for kind in ('missing_node', 'bad_diagonal', 'bad_window', 'duplicate_id'):
            with self.subTest(kind=kind):
                problem = example()
                if kind == 'missing_node':
                    del problem['travel_time_s']['UAV']['A']['B']
                elif kind == 'bad_diagonal':
                    problem['travel_time_s']['AGV']['D']['D'] = 1
                elif kind == 'bad_window':
                    problem['tasks'][0].update(earliest_s=10, latest_s=9)
                else:
                    problem['tasks'][1]['id'] = 'T1'
                with self.assertRaises(InputError):
                    validate_problem(problem)

    def test_json_duplicate_keys_and_nan_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.json'
            for text in ('{"schema_version": 1, "schema_version": 2}', '{"a": NaN}'):
                file.write_text(text, encoding='utf-8')
                with self.assertRaises(InputError):
                    read_json(file)

    def test_optional_distance_is_never_invented(self):
        problem = example()
        self.assertIsNone(trip(problem)['distance_m'])
        problem['distance_m'] = copy.deepcopy(problem['travel_time_s'])
        problem['distance_m']['UAV']['D']['A'] = 12.5
        validate_problem(problem)
        self.assertEqual(trip(problem)['distance_m'], 27.5)
        problem['distance_m']['UAV']['A']['D'] = None
        self.assertTrue(trip(problem)['valid'])
        self.assertIsNone(trip(problem)['distance_m'])

    def test_demo_cli_roundtrip(self):
        problem = load_problem(ROOT / 'data' / 'demo_2026.json')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'plan.json'
            command = [sys.executable, str(ROOT / 'run_ontime.py')]
            created = subprocess.run([*command, 'schedule', str(ROOT / 'data' / 'demo_2026.json'),
                                      '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stderr)
            saved = read_json(output)
            self.assertEqual(saved['mode'], 'soft')
            self.assertTrue(evaluate_plan(problem, saved['plan_input'])['valid'])
            checked = subprocess.run([*command, 'evaluate', str(ROOT / 'data' / 'demo_2026.json'),
                                      str(output)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertTrue(json.loads(checked.stdout)['valid'])

    def test_cli_preserves_exported_hard_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'plan.json'
            command = [sys.executable, str(ROOT / 'run_ontime.py')]
            source = str(ROOT / 'data' / 'demo_2026.json')
            created = subprocess.run([*command, 'schedule', source, '--mode', 'hard',
                                      '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stderr)
            checked = subprocess.run([*command, 'evaluate', source, str(output)],
                                     capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['mode'], 'hard')

    def test_cli_invalid_hard_plan_has_nonzero_exit(self):
        problem = example()
        problem['tasks'][0]['latest_s'] = 19
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            plan = Path(directory) / 'plan.json'
            source.write_text(json.dumps(problem), encoding='utf-8')
            plan.write_text(json.dumps({'trips': [{'trip_id': '1', 'vehicle_id': 'U1',
                            'task_ids': ['T1'], 'load_start_s': 0}]}), encoding='utf-8')
            checked = subprocess.run([sys.executable, str(ROOT / 'run_ontime.py'), 'evaluate',
                                     str(source), str(plan), '--mode', 'hard'],
                                     capture_output=True, text=True)
            self.assertEqual(checked.returncode, 2, checked.stderr)
            result = json.loads(checked.stdout)
            self.assertFalse(result['valid'])
            self.assertIn('time_window', failed(result['trips'][0]))


if __name__ == '__main__':
    unittest.main()
