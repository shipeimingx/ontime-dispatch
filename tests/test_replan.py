"""Functional checkpoint tests, not user usability tests or hardware trials."""
import copy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from test_ontime import example, trip
from ontime.evaluate import check_plan
from ontime.ga import GAParameters
from ontime.input import InputError, as_problem
from ontime.models import Plan, Trip, UnassignedTask
from ontime.replan import replan_at_checkpoint, validate_replanning
from ontime.scheduler import schedule


def checkpoint_fixture():
    data = example()
    data['vehicles'][0]['capacity_kg'] = 2
    data['vehicles'].append({**data['vehicles'][0], 'id': 'U2'})
    data['tasks'].append({**data['tasks'][0], 'id': 'T3'})
    data['tasks'].append({**data['tasks'][1], 'id': 'T4'})
    problem = as_problem(data)
    baseline = Plan((Trip('done', 'U1', ('T1',), 0),
                     Trip('active', 'U2', ('T2',), 30),
                     Trip('future', 'U1', ('T3',), 90)),
                    (UnassignedTask('T4', 'not_in_plan', 'input omission explicitly recorded'),), 'soft', 2026)
    assert check_plan(problem, baseline).valid
    return problem, baseline


class ExplicitBoundaryTests(unittest.TestCase):
    def test_dictionary_adapter_cannot_override_device_capacity(self):
        from ontime.evaluate import evaluate_trip
        data = example()
        data['vehicles'][0]['capacity_kg'] = 3
        forged = {**data['vehicles'][0], 'capacity_kg': 4}
        with self.assertRaises(InputError):
            evaluate_trip(data, forged, ['T1', 'T2'], 0, 'soft')

    def test_single_task_normal_delivery(self):
        data = example()
        data['tasks'] = data['tasks'][:1]
        result = schedule(data, 'hard', 2026)
        self.assertTrue(result['valid'] and result['complete'])
        stop = result['trips'][0]['stops'][0]
        self.assertEqual((stop['arrival_s'], stop['completion_s']), (20, 25))
        self.assertEqual(result['trips'][0]['return_s'], 40)

    def test_all_tasks_unassignable_are_retained(self):
        data = example()
        for task in data['tasks']:
            task['demand_kg'] = 999
        result = schedule(data, 'soft', 2026)
        self.assertTrue(result['valid'])
        self.assertEqual(result['trips'], [])
        self.assertEqual(set(result['unassigned_task_ids']), {'T1', 'T2'})
        self.assertTrue(all(u['reason_code'] == 'payload_exceeded' for u in result['unassigned']))

    def test_early_wait_is_feasible_and_counted(self):
        data = example()
        data['tasks'][0]['earliest_s'] = 100
        result = trip(data)
        self.assertTrue(result['valid'])
        self.assertEqual(result['stops'][0]['waiting_s'], 80)
        self.assertEqual(result['stops'][0]['service_start_s'], 100)
        self.assertEqual(result['return_s'], 120)


class ReplanningTests(unittest.TestCase):
    def setUp(self):
        self.problem, self.baseline = checkpoint_fixture()
        self.parameters = GAParameters(population_size=6, elite_count=1, tournament_size=2,
                                       max_generations=3, patience=2, seed=2026)

    def run_demo(self):
        return replan_at_checkpoint(self.problem, self.baseline, 50, 'U1', self.parameters)

    def test_completed_and_active_loaded_tasks_are_frozen(self):
        result = self.run_demo()
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['completed_task_ids'], ['T1'])
        self.assertEqual(result['locked_unfinished_task_ids'], ['T2'])
        self.assertEqual(result['adjustable_task_ids'], ['T3', 'T4'])
        actual = {t['trip_id']: t for t in result['combined']['plan_input']['trips']}
        for trip in self.baseline.trips[:2]:
            self.assertEqual(actual[trip.trip_id], trip.to_dict())
        self.assertEqual(result['combined']['summary']['assigned_count'], 4)
        states = {t['task_id']: t['state'] for t in result['task_states']}
        self.assertEqual(states, {'T1':'simulated_completed', 'T2':'locked_unfinished',
                                  'T3':'candidate_not_approved', 'T4':'candidate_not_approved'})
        self.assertEqual(len(result['combined']['assigned_task_ids']), 4)
        new = [t for t in result['combined']['trips'] if t['trip_id'].startswith('replan-')]
        self.assertTrue(all(t['vehicle_id'] == 'U2' and t['load_start_s'] >= 120 for t in new))
        self.assertTrue(any(s['executed_s'] > 0 for s in result['frozen_segments']))
        self.assertTrue(any(s['executed_s'] == 0 for s in result['frozen_segments']))
        self.assertTrue(all(s['executed_until_s'] is None or s['executed_until_s'] <= 50
                            for s in result['frozen_segments']))

    def test_unapproved_and_fixed_seed_reproducible(self):
        result = self.run_demo()
        self.assertEqual(result, self.run_demo())
        self.assertEqual(result['approval_status'], 'not_approved')
        self.assertTrue(result['requires_human_approval'])
        self.assertFalse(result['execution_started'])

    def test_active_failed_device_is_explicitly_rejected(self):
        with self.assertRaisesRegex(InputError, 'Active-device failure'):
            replan_at_checkpoint(self.problem, self.baseline, 50, 'U2', self.parameters)

    def test_tampered_frozen_or_new_failed_vehicle_is_rejected(self):
        result = self.run_demo()
        from ontime.evaluate import parse_plan
        candidate = parse_plan(self.problem, result['combined']['plan_input'], 'soft', 2026)
        trips = list(candidate.trips)
        index = next(i for i, t in enumerate(trips) if t.trip_id == 'done')
        trips[index] = replace(trips[index], load_start_s=1)
        self.assertFalse(validate_replanning(self.problem, self.baseline, replace(candidate, trips=tuple(trips)),
                                            50, 'U1')['valid'])
        trips = list(candidate.trips)
        index = next(i for i, t in enumerate(trips) if t.trip_id.startswith('replan-'))
        trips[index] = replace(trips[index], vehicle_id='U1')
        self.assertFalse(validate_replanning(self.problem, self.baseline, replace(candidate, trips=tuple(trips)),
                                            50, 'U1')['valid'])

    def test_checkpoint_after_all_shifts_closes_devices_without_invalid_interval(self):
        result = replan_at_checkpoint(self.problem, self.baseline, 600, 'U1', self.parameters)
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['completed_task_ids'], ['T1', 'T2', 'T3'])
        self.assertEqual(result['combined']['unassigned_task_ids'], ['T4'])

    def test_exact_load_start_event_precedes_loading(self):
        result = replan_at_checkpoint(self.problem, self.baseline, 0, 'U1', self.parameters)
        self.assertEqual(result['frozen_trip_ids'], [])
        self.assertEqual(result['completed_task_ids'], [])
        self.assertEqual(len(result['adjustable_task_ids']), 4)
        self.assertTrue(result['validation']['valid'])

    def test_invalid_checkpoint_and_baseline_rejected(self):
        for event, vehicle in ((-1, 'U1'), (True, 'U1'), (50, 'missing')):
            with self.assertRaises(InputError):
                replan_at_checkpoint(self.problem, self.baseline, event, vehicle, self.parameters)
        invalid = replace(self.baseline, unassigned=())
        with self.assertRaises(InputError):
            replan_at_checkpoint(self.problem, invalid, 50, 'U1', self.parameters)


if __name__ == '__main__':
    unittest.main()
