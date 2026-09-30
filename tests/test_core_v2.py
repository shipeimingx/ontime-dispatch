"""Meaningful regressions for insertion, typed plans, seed control and exports."""

from dataclasses import replace
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from test_ontime import example
from ontime import Evaluation, Plan, ScheduledStop, Task, Trip, Vehicle
from ontime.evaluate import check_plan
from ontime.export import export_results
from ontime.generate import synthetic_cases
from ontime.input import InputError, as_problem, validate_problem
from ontime.scheduler import construct_plan, schedule


class InsertionTests(unittest.TestCase):
    def test_middle_insertion_feasible_when_appending_and_new_trip_are_not(self):
        data = example()
        data['stations'] = ['A', 'B', 'C']
        data['vehicles'][0].update(capacity_kg=10, load_s=0, depot_unload_s=0,
                                   turnaround_s=0, trip_limit_s=100)
        data['tasks'] = [{**data['tasks'][0], 'id': f'T{i}', 'station_id': node,
                          'demand_kg': 1, 'latest_s': i * 100, 'unload_s': 0, 'service_s': 0}
                         for i, node in enumerate(('A', 'B', 'C'), 1)]
        rows = {'D': {'D': 0, 'A': 10, 'B': 50, 'C': 80},
                'A': {'D': 10, 'A': 0, 'B': 10, 'C': 1},
                'B': {'D': 10, 'A': 50, 'B': 0, 'C': 80},
                'C': {'D': 80, 'A': 80, 'B': 1, 'C': 0}}
        data['travel_time_s'] = {'UAV': rows, 'AGV': copy.deepcopy(rows)}
        result = schedule(data, 'hard', 2026)
        self.assertTrue(result['valid'])
        self.assertTrue(result['complete'])
        self.assertEqual(result['trips'][0]['task_ids'], ['T1', 'T3', 'T2'])
        self.assertEqual(result['trips'][0]['mission_s'], 22)

    def test_insertion_must_protect_previously_assigned_window(self):
        data = example()
        data['vehicles'][0].update(load_s=0, depot_unload_s=0, turnaround_s=0)
        data['tasks'][0].update(earliest_s=100, latest_s=100, unload_s=0, service_s=0)
        data['tasks'][1].update(earliest_s=0, latest_s=150, unload_s=0, service_s=0)
        rows = {'D': {'D': 0, 'A': 10, 'B': 100},
                'A': {'D': 10, 'A': 0, 'B': 100}, 'B': {'D': 10, 'A': 10, 'B': 0}}
        data['travel_time_s'] = {'UAV': rows, 'AGV': copy.deepcopy(rows)}
        result = schedule(data, 'hard')
        self.assertTrue(result['valid'])
        self.assertEqual(result['assigned_task_ids'], ['T1'])
        self.assertEqual(result['unassigned_task_ids'], ['T2'])
        failures = [c for attempt in result['unassigned'][0]['attempts'] for c in attempt['failed_checks']]
        self.assertTrue(any(c['code'] == 'time_window' and c['task_id'] == 'T1' for c in failures))

    def test_lateness_cost_uses_explicit_weight(self):
        data = example()
        data['tasks'] = [data['tasks'][0]]
        data['tasks'][0].update(latest_s=19, lateness_cost_per_s=7)
        result = schedule(data, 'soft')
        self.assertEqual(result['summary']['lateness_s'], 1)
        self.assertEqual(result['summary']['lateness_cost'], 7)
        self.assertTrue(result['valid'])

    def test_seed_reproducible_and_used_only_for_ties(self):
        data = example()
        data['tasks'] = [data['tasks'][0]]
        data['vehicles'].append({**data['vehicles'][0], 'id': 'U2'})
        for seed in range(5):
            self.assertEqual(schedule(data, seed=seed), schedule(data, seed=seed))
        allocations = {schedule(data, seed=seed)['trips'][0]['vehicle_id'] for seed in range(10)}
        self.assertEqual(allocations, {'U1', 'U2'})


class TypedPlanTests(unittest.TestCase):
    def test_typed_records_and_independent_recompute(self):
        problem = as_problem(example())
        self.assertIsInstance(problem.tasks[0], Task)
        self.assertIsInstance(problem.vehicles[0], Vehicle)
        plan = construct_plan(problem)
        self.assertIsInstance(plan, Plan)
        self.assertIsInstance(plan.trips[0], Trip)
        checked = check_plan(problem, plan)
        self.assertIsInstance(checked, Evaluation)
        self.assertIsInstance(checked.trips[0].stops[0], ScheduledStop)
        self.assertTrue(checked.valid)
        bad = replace(plan, trips=(replace(plan.trips[0], load_start_s=499),))
        self.assertFalse(check_plan(problem, bad).valid)

    def test_explicit_coverage_cannot_drop_or_double_classify_task(self):
        problem = as_problem(example())
        plan = Plan((Trip('p1', 'U1', ('T1',), 0),), ())
        result = check_plan(problem, plan)
        self.assertFalse(result.valid)
        failure = next(c for c in result.checks if c.code == 'all_tasks_accounted_for')
        self.assertEqual(failure.evidence['missing_task_ids'], ['T2'])
        from ontime.models import UnassignedTask
        bad = replace(plan, unassigned=(UnassignedTask('T1', 'test', 'test'),
                                         UnassignedTask('T2', 'test', 'test')))
        self.assertFalse(check_plan(problem, bad).valid)

    def test_typed_invalid_vehicle_is_validated(self):
        problem = as_problem(example())
        bad = replace(problem, vehicles=(replace(problem.vehicles[0], load_s=-1),))
        with self.assertRaises(InputError):
            construct_plan(bad)


class ScenarioAndExportTests(unittest.TestCase):
    def test_seeded_cases_and_units(self):
        first = synthetic_cases(2026)
        self.assertEqual(first, synthetic_cases(2026))
        self.assertNotEqual(first['normal']['distance_m'], synthetic_cases(2027)['normal']['distance_m'])
        normal = first['normal']
        self.assertEqual(len(normal['tasks']), 8)
        self.assertEqual([v['type'] for v in normal['vehicles']], ['UAV', 'UAV', 'AGV', 'AGV'])
        for value in first.values():
            validate_problem(value)
        for mutation in ('wrong_unit', 'missing_speed', 'negative_speed', 'missing_cost'):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(normal)
                if mutation == 'wrong_unit':
                    data['units']['time'] = 'min'
                elif mutation == 'missing_speed':
                    del data['vehicles'][0]['speed_m_s']
                elif mutation == 'negative_speed':
                    data['vehicles'][0]['speed_m_s'] = -1
                else:
                    del data['tasks'][0]['lateness_cost_per_s']
                with self.assertRaises(InputError):
                    validate_problem(data)

    def test_speed_does_not_silently_replace_supplied_time_matrix(self):
        data = synthetic_cases()['normal']
        baseline = schedule(data, seed=2026)
        changed = copy.deepcopy(data)
        for vehicle in changed['vehicles']:
            vehicle['speed_m_s'] *= 2
        result = schedule(changed, seed=2026)
        self.assertEqual(result['summary'], baseline['summary'])
        self.assertEqual(result['plan_input'], baseline['plan_input'])

    def test_abnormal_cases_keep_all_tasks_and_enforce_hard_rules(self):
        for name, data in synthetic_cases().items():
            for mode in ('hard', 'soft'):
                with self.subTest(name=name, mode=mode):
                    result = schedule(data, mode, 2026)
                    self.assertTrue(result['valid'])
                    planned, omitted = result['assigned_task_ids'], result['unassigned_task_ids']
                    self.assertEqual(len(planned) + len(omitted), 8)
                    self.assertFalse(set(planned) & set(omitted))
                    self.assertEqual(len(planned), sum(len(t['task_ids']) for t in result['trips']))
                    if mode == 'hard':
                        self.assertEqual(result['summary']['lateness_s'], 0)
                    if name == 'overload':
                        target = next(u for u in result['unassigned'] if u['task_id'] == 'T08')
                        self.assertEqual(target['reason_code'], 'payload_exceeded')
                    if name == 'window_conflict' and mode == 'hard':
                        target = next(u for u in result['unassigned'] if u['task_id'] == 'T01')
                        self.assertEqual(target['reason_code'], 'time_window_conflict')
                    if name == 'window_conflict' and mode == 'soft':
                        self.assertGreater(result['summary']['lateness_cost'], 0)
                    if name == 'unavailable':
                        self.assertFalse(any(t['type'] == 'UAV' for t in result['trips']))
                        self.assertTrue(all(u['reason_code'] == 'device_unavailable'
                                            for u in result['unassigned']))

    def test_json_csv_roundtrip_and_empty_table_headers(self):
        result = schedule(synthetic_cases()['normal'], seed=2026)
        with tempfile.TemporaryDirectory() as directory:
            export_results(result, directory)
            directory = Path(directory)
            loaded = json.loads((directory / 'plan.json').read_text(encoding='utf-8'))
            self.assertEqual(loaded, result)
            with (directory / 'stops.csv').open(encoding='utf-8-sig', newline='') as file:
                stops = list(csv.DictReader(file))
            self.assertEqual(len(stops), result['summary']['assigned_count'])
            self.assertEqual(sum(float(s['lateness_cost']) for s in stops),
                             result['summary']['lateness_cost'])
            with (directory / 'unassigned.csv').open(encoding='utf-8-sig', newline='') as file:
                reader = csv.DictReader(file)
                self.assertIn('task_id', reader.fieldnames)
                self.assertEqual(len(list(reader)), result['summary']['unassigned_count'])

    def test_cli_output_directory_and_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'problem.json'
            file.write_text(json.dumps(synthetic_cases()['overload']), encoding='utf-8')
            output = Path(directory) / 'results'
            run = subprocess.run([sys.executable, str(ROOT / 'run_ontime.py'), 'schedule', str(file),
                                  '--mode', 'hard', '--seed', '2026', '--output-dir', str(output)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
            self.assertEqual(result['seed'], 2026)
            self.assertEqual(result['mode'], 'hard')
            self.assertTrue((output / 'checks.csv').exists())
            check = subprocess.run([sys.executable, str(ROOT / 'run_ontime.py'), 'evaluate', str(file),
                                    str(output / 'plan.json')], capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(json.loads(check.stdout)['seed'], 2026)


if __name__ == '__main__':
    unittest.main()
