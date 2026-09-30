"""Standard-library CLI; candidate generation does not execute deliveries."""

import argparse
import json
import sys
from pathlib import Path

from . import PROFILE
from .evaluate import check_plan, parse_plan
from .export import export_results, export_two_stage, write_json
from .ga import CostParameters, GAParameters, run_two_stage
from .generate import generate_files
from .input import InputError, load_instance, read_json
from .scheduler import schedule
from .replan import export_replanning, replan_at_checkpoint


def main(argv=None):
    parser = argparse.ArgumentParser(description='OnTime Dispatch — new 2026 illustrative Python model')
    sub = parser.add_subparsers(dest='command', required=True)
    generate = sub.add_parser('generate', help='Write normal + three abnormal synthetic JSON inputs')
    generate.add_argument('--seed', type=int, default=2026)
    generate.add_argument('--output-dir', type=Path, default=Path('data/cases'))
    replan = sub.add_parser('replan', help='Simulated depot checkpoint; export an unapproved candidate')
    replan.add_argument('input', type=Path)
    replan.add_argument('plan', type=Path)
    replan.add_argument('--checkpoint-s', type=int, required=True)
    replan.add_argument('--unavailable-vehicle', required=True)
    replan.add_argument('--seed', type=int, default=2026)
    replan.add_argument('--output-dir', type=Path, required=True)
    optimize = sub.add_parser('optimize', help='Run heuristic then permutation GA on the same input')
    optimize.add_argument('input', type=Path)
    optimize.add_argument('--mode', choices=('soft', 'hard'))
    optimize.add_argument('--seed', type=int, default=2026)
    optimize.add_argument('--output-dir', type=Path, required=True)
    optimize.add_argument('--population-size', type=int, default=24)
    optimize.add_argument('--generations', type=int, default=40)
    optimize.add_argument('--elite-count', type=int, default=2)
    optimize.add_argument('--tournament-size', type=int, default=3)
    optimize.add_argument('--crossover-rate', type=float, default=0.9)
    optimize.add_argument('--mutation-rate', type=float, default=0.25)
    optimize.add_argument('--patience', type=int, default=12)
    optimize.add_argument('--uav-transport-per-s', type=float, default=0.02)
    optimize.add_argument('--agv-transport-per-s', type=float, default=0.01)
    optimize.add_argument('--lateness-multiplier', type=float, default=1.0)
    for command in ('validate', 'schedule', 'evaluate'):
        child = sub.add_parser(command)
        child.add_argument('input', type=Path)
        if command != 'validate':
            child.add_argument('--mode', choices=('soft', 'hard'))
            child.add_argument('--seed', type=int, help='Heuristic tie-break seed (default 0); evaluation metadata only')
            group = child.add_mutually_exclusive_group()
            group.add_argument('--output', type=Path, help='Single JSON export (legacy option)')
            group.add_argument('--output-dir', type=Path, help='JSON and CSV result directory')
        if command == 'evaluate':
            child.add_argument('plan', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'generate':
            names = generate_files(args.output_dir, args.seed)
            print(json.dumps({'generated': names, 'seed': args.seed,
                              'output_dir': str(args.output_dir.resolve())}))
            return 0
        problem = load_instance(args.input)
        if args.command == 'replan':
            raw = read_json(args.plan)
            if not isinstance(raw, dict):
                raise InputError('plan: expected JSON object')
            baseline = parse_plan(problem, raw.get('plan_input', raw), raw.get('mode', problem.window_mode),
                                  raw.get('seed', args.seed))
            result = replan_at_checkpoint(problem, baseline, args.checkpoint_s, args.unavailable_vehicle,
                                          GAParameters(seed=args.seed))
            export_replanning(result, args.output_dir)
            print(json.dumps({'valid': result['validation']['valid'], 'approval_status': result['approval_status'],
                              'completed_task_ids': result['completed_task_ids'],
                              'locked_unfinished_task_ids': result['locked_unfinished_task_ids'],
                              'unassigned_task_ids': result['combined']['unassigned_task_ids']}, ensure_ascii=False))
            return 0
        if args.command == 'optimize':
            parameters = GAParameters(args.population_size, args.generations, args.elite_count,
                                      args.tournament_size, args.crossover_rate, args.mutation_rate,
                                      args.patience, args.seed)
            costs = CostParameters(args.uav_transport_per_s, args.agv_transport_per_s, args.lateness_multiplier)
            run = run_two_stage(problem, args.mode, parameters, costs)
            export_two_stage(run, args.output_dir)
            print(json.dumps({'output_dir': str(args.output_dir.resolve()), 'mode': run['mode'],
                              'generations_completed': run['generations_completed'],
                              'stop_reason': run['stop_reason'], 'improved': run['comparison']['improved'],
                              'initial': run['comparison']['initial_objective'],
                              'ga': run['comparison']['ga_objective']}, ensure_ascii=False))
            return 0
        if args.command == 'validate':
            result = {'input_valid': True, 'feasibility_checked': False,
                      'schema_version': problem.schema_version,
                      'tasks': len(problem.tasks), 'vehicles': len(problem.vehicles)}
        elif args.command == 'schedule':
            result = schedule(problem, args.mode, 0 if args.seed is None else args.seed)
        else:
            raw = read_json(args.plan)
            chosen_mode = args.mode
            chosen_seed = 0 if args.seed is None else args.seed
            if isinstance(raw, dict) and 'plan_input' in raw:
                if raw.get('profile') not in (PROFILE, 'python-demo-2026-v1'):
                    raise InputError('plan.profile: unsupported exported model profile')
                chosen_mode = chosen_mode or raw.get('mode')
                chosen_seed = raw.get('seed', 0) if args.seed is None else args.seed
                raw = raw['plan_input']
            plan = parse_plan(problem, raw, chosen_mode, chosen_seed)
            result = check_plan(problem, plan).to_dict()
            result['scenario_label'] = problem.scenario_label
        if getattr(args, 'output_dir', None):
            export_results(result, args.output_dir)
            print(f'Saved JSON/CSV to {args.output_dir.resolve()}')
        elif getattr(args, 'output', None):
            write_json(args.output, result)
            print(f'Saved {args.output.resolve()}')
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if (getattr(args, 'output_dir', None) or getattr(args, 'output', None)) and 'summary' in result:
            print(json.dumps({'valid': result['valid'], 'complete': result['complete'],
                              'coverage': result['coverage'], 'mode': result['mode'],
                              'seed': result['seed'], **result['summary']}, ensure_ascii=False))
        return 0 if result.get('valid', True) else 2
    except (InputError, OSError, OverflowError) as exc:
        print(f'Input/output error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
