"""Two-stage linkage, order-aware decoding, constrained fitness and GA archives."""

from dataclasses import replace
import copy
import csv
from fractions import Fraction
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from test_ontime import example
from ontime.evaluate import check_plan
from ontime.export import export_two_stage
from ontime.ga import (CostParameters, GAParameters, decode_chromosome, mutate,
                       objective_from_evaluation, order_crossover, run_two_stage)
from ontime.generate import synthetic_cases
from ontime.input import InputError, as_problem, validate_problem
from ontime.models import Plan, UnassignedTask
from ontime.scheduler import construct_plan, urgency_order

SMALL = GAParameters(population_size=8, max_generations=4, elite_count=2, tournament_size=3,
                     patience=0, seed=2026)


class LinkageTests(unittest.TestCase):
    def test_seed_is_actual_first_stage_and_roundtrips(self):
        problem = as_problem(synthetic_cases()['normal'])
        run = run_two_stage(problem, 'soft', SMALL)
        initial = construct_plan(problem, 'soft', SMALL.seed)
        self.assertEqual(run['initial']['plan_input'], initial.to_dict())
        self.assertEqual(run['heuristic_seed']['chromosome'], list(urgency_order(problem)))
        self.assertTrue(run['heuristic_seed']['decoded_plan_matches_initial'])
        self.assertEqual(run['initial_population'][0]['source'], 'heuristic_seed')
        self.assertEqual(run['initial_population'][0]['objective'], run['initial']['objective'])
        self.assertEqual({i['source'] for i in run['initial_population']},
                         {'heuristic_seed', 'perturbed_heuristic', 'random_permutation'})

    def test_decoder_uses_order_and_fixed_decoder_seed(self):
        data = example()
        data['vehicles'][0].update(capacity_kg=2, available_until_s=80)
        problem = as_problem(data)
        first = decode_chromosome(problem, ('T1', 'T2'), 'hard', 2026)
        second = decode_chromosome(problem, ('T2', 'T1'), 'hard', 2026)
        self.assertEqual(first.trips[0].task_ids, ('T1',))
        self.assertEqual(second.trips[0].task_ids, ('T2',))
        self.assertNotEqual(first, second)
        self.assertEqual(second, decode_chromosome(problem, ('T2', 'T1'), 'hard', 2026))
        self.assertTrue(check_plan(problem, first).valid)
        self.assertTrue(check_plan(problem, second).valid)

    def test_bad_chromosomes_rejected(self):
        for genes in (None, 'T1,T2', ('T1',), ('T1', 'T1'), ('T1', 'unknown'), ('T1', 2)):
            with self.subTest(genes=genes), self.assertRaises(InputError):
                decode_chromosome(example(), genes)


class OperatorsAndFitnessTests(unittest.TestCase):
    def test_ox_swap_and_insertion_preserve_every_gene(self):
        rng = random.Random(2026)
        for size in range(10):
            parent = tuple(f'T{i}' for i in range(size))
            for _ in range(25):
                other = list(parent)
                rng.shuffle(other)
                crossed = order_crossover(parent, tuple(other), rng)
                for changed in (crossed, mutate(crossed, rng, 'swap'), mutate(crossed, rng, 'insert')):
                    self.assertEqual(len(changed), len(parent))
                    self.assertEqual(set(changed), set(parent))

    def test_coverage_precedes_arbitrarily_high_cost(self):
        problem = as_problem(example())
        complete = construct_plan(problem)
        empty = Plan((), tuple(UnassignedTask(t.id, 'test', 'Test omission') for t in problem.tasks))
        costs = CostParameters(uav_transport_per_s=10000, agv_transport_per_s=10000)
        served = objective_from_evaluation(problem, check_plan(problem, complete), costs)
        omitted = objective_from_evaluation(problem, check_plan(problem, empty), costs)
        self.assertGreater(served.total_cost, omitted.total_cost)
        self.assertLess(served, omitted)

    def test_explicit_transport_and_lateness_units_and_invalid_plan_gate(self):
        data = example()
        data['tasks'] = [data['tasks'][0]]
        data['tasks'][0].update(latest_s=19, lateness_cost_per_s=7)
        problem = as_problem(data)
        plan = construct_plan(problem, 'soft')
        costs = CostParameters(0.02, 0.01, 3)
        objective = objective_from_evaluation(problem, check_plan(problem, plan), costs)
        self.assertEqual(objective.transport_cost, Fraction('0.02') * 25)
        self.assertEqual(objective.lateness_penalty, 21)
        self.assertEqual(objective.total_cost, Fraction('21.5'))
        with self.assertRaises(InputError):
            objective_from_evaluation(problem, check_plan(problem, replace(plan, mode='hard')), costs)


class EvolutionTests(unittest.TestCase):
    def test_archive_history_reproducible_and_all_constraint_modes(self):
        for name, data in synthetic_cases().items():
            for mode in ('hard', 'soft'):
                with self.subTest(name=name, mode=mode):
                    run = run_two_stage(data, mode, SMALL)
                    self.assertTrue(run['initial']['valid'])
                    self.assertTrue(run['ga']['valid'])
                    initial = run['initial']['objective']
                    previous = (initial['unassigned_count'], initial['total_cost'])
                    for row in run['iterations']:
                        best = row['best_known']
                        current = (best['unassigned_count'], best['total_cost'])
                        self.assertLessEqual(current, previous)
                        previous = current
                    self.assertEqual(len(run['comparison']['tasks']), 8)
                    if mode == 'hard':
                        self.assertEqual(run['ga']['summary']['lateness_s'], 0)
                    if name == 'overload':
                        self.assertIn('T08', run['ga']['unassigned_task_ids'])
                    if name == 'unavailable':
                        self.assertFalse(any(t['type'] == 'UAV' for t in run['ga']['trips']))
        normal = synthetic_cases()['normal']
        self.assertEqual(run_two_stage(normal, parameters=SMALL), run_two_stage(normal, parameters=SMALL))

    def test_no_improvement_retains_initial_plan_and_stops(self):
        data = example()
        for rows in data['travel_time_s'].values():
            for start, row in rows.items():
                for end in row:
                    row[end] = 0 if start == end else 10
        params = replace(SMALL, max_generations=10, patience=2, crossover_rate=0, mutation_rate=0)
        run = run_two_stage(data, parameters=params)
        self.assertFalse(run['comparison']['improved'])
        self.assertEqual(run['initial']['plan_input'], run['ga']['plan_input'])
        self.assertEqual(run['generations_completed'], 2)
        self.assertEqual(run['stop_reason'], 'stagnation_patience')

    def test_zero_generations_and_trivial_permutation_terminate(self):
        run = run_two_stage(example(), parameters=replace(SMALL, max_generations=0))
        self.assertEqual(run['generations_completed'], 0)
        self.assertEqual(len(run['iterations']), 1)
        data = example()
        data['tasks'] = []
        run = run_two_stage(data, parameters=SMALL)
        self.assertEqual(run['stop_reason'], 'permutation_space_trivial')
        self.assertTrue(run['ga']['complete'])

    def test_parameters_reject_invalid_probabilities_counts_and_costs(self):
        for changes in ({'elite_count': 0}, {'population_size': 1}, {'tournament_size': 99},
                        {'patience': -1}, {'mutation_rate': float('nan')}, {'crossover_rate': 1.1}):
            with self.subTest(changes=changes), self.assertRaises(InputError):
                run_two_stage(example(), parameters=replace(SMALL, **changes))
        with self.assertRaises(InputError):
            run_two_stage(example(), costs=CostParameters(uav_transport_per_s=-1))


class ExportTests(unittest.TestCase):
    def test_outputs_include_two_plans_task_comparison_and_generation_zero(self):
        run = run_two_stage(synthetic_cases()['normal'], parameters=SMALL)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            export_two_stage(run, directory)
            for phase in ('initial', 'ga'):
                result = json.loads((directory / phase / 'plan.json').read_text(encoding='utf-8'))
                self.assertEqual(result, run[phase])
                self.assertTrue(result['valid'])
            with (directory / 'iterations.csv').open(encoding='utf-8-sig', newline='') as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(int(rows[0]['generation']), 0)
            self.assertEqual(len(rows), run['generations_completed'] + 1)
            self.assertIn('best_known_total_cost', rows[0])
            with (directory / 'task-comparison.csv').open(encoding='utf-8-sig', newline='') as file:
                tasks = list(csv.DictReader(file))
            self.assertEqual(len(tasks), 8)
            self.assertTrue((directory / 'initial-population.json').exists())
            snapshot = json.loads((directory / 'input-snapshot.json').read_text(encoding='utf-8'))
            validate_problem(snapshot)
            import hashlib
            canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                   separators=(',', ':')).encode('utf-8')
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), run['input_snapshot_sha256'])

    def test_cli_optimize_and_evaluate_exported_ga_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            command = [sys.executable, str(ROOT / 'run_ontime.py')]
            source = str(ROOT / 'data/cases/normal.json')
            optimized = subprocess.run([*command, 'optimize', source, '--mode', 'hard', '--seed', '2026',
                '--population-size', '8', '--generations', '2', '--output-dir', str(output)],
                capture_output=True, text=True)
            self.assertEqual(optimized.returncode, 0, optimized.stderr)
            checked = subprocess.run([*command, 'evaluate', source, str(output / 'ga/plan.json')],
                                     capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertTrue(json.loads(checked.stdout)['valid'])


if __name__ == '__main__':
    unittest.main()
