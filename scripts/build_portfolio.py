"""One recorded illustrative run -> checked plans, checkpoint extension and editable figures."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from ontime.evaluate import check_plan, parse_plan
from ontime.export import export_two_stage, write_json
from ontime.ga import GAParameters, run_two_stage
from ontime.generate import synthetic_cases
from ontime.input import as_problem
from ontime.replan import export_replanning, replan_at_checkpoint


def portfolio_input(seed):
    data = synthetic_cases(seed)['overload']
    data['scenario_label'] = 'Illustrative data — portfolio checkpoint demonstration (2026 new implementation)'
    for vehicle in data['vehicles']:
        if vehicle['id'] == 'UAV-02':
            vehicle['available_from_s'] = 240
        if vehicle['id'] == 'AGV-02':
            vehicle['available_from_s'] = 600
    data['metadata'].update(portfolio_generator='portfolio_v1', checkpoint_s=200,
                            failed_vehicle_id='UAV-02',
                            portfolio_changes={'T08_demand_kg': 60, 'UAV-02_available_from_s': 240,
                                               'AGV-02_available_from_s': 600},
                            rationale='2026 demonstration assumptions: expose unassigned payload and a depot failure before UAV-02 loading; preserve other active trips')
    return data


def build(output, seed=2026, render=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    data = portfolio_input(seed)
    write_json(ROOT / 'data' / 'portfolio.json', data)
    problem = as_problem(data)
    params = GAParameters(seed=seed)
    run = run_two_stage(problem, parameters=params)
    export_two_stage(run, output)
    checks = []
    for phase in ('initial', 'ga'):
        plan = parse_plan(problem, run[phase]['plan_input'], run['mode'], seed)
        checked = check_plan(problem, plan).to_dict()
        assert checked['valid']
        write_json(output / phase / 'checked.json', checked)
        checks.append({'phase': phase, 'valid': checked['valid']})
    # Repeat the full search, not just export comparison.
    repeated = run_two_stage(problem, parameters=params)
    if repeated != run:
        raise RuntimeError('Full fixed-seed run failed reproducibility check')
    write_json(output / 'reproducibility.json', {'seed': seed, 'full_run_equal': True,
                                                'input_sha256': run['input_snapshot_sha256'],
                                                'scope': 'entire two-stage run, including population and iterations'})
    baseline = parse_plan(problem, run['ga']['plan_input'], run['mode'], seed)
    replanned = replan_at_checkpoint(problem, baseline, 200, 'UAV-02', params)
    repeated_replan = replan_at_checkpoint(problem, baseline, 200, 'UAV-02', params)
    if repeated_replan != replanned:
        raise RuntimeError('Fixed-seed checkpoint run failed reproduction')
    export_replanning(replanned, output / 'replan')
    figures = []
    presentation_runtime = None
    if render:
        from portfolio_figures import render_figures
        # Read the persisted run: all five views share exactly this run.json.
        figures = render_figures(output / 'run.json', output / 'replan' / 'replan.json', output / 'figures')
        import PIL
        from PIL import features
        presentation_runtime = {'Pillow': PIL.__version__, 'FreeType': features.version('freetype2')}
    sources = [*(ROOT / 'src' / 'ontime').glob('*.py'), *(ROOT / 'scripts').glob('*.py'),
               *(ROOT / 'tests').glob('test_*.py'), *(ROOT.glob('*.cmd')),
               ROOT / 'run_ontime.py', ROOT / 'requirements-presentation.txt']
    manifest = {'python': platform.python_version(), 'seed': seed, 'mode': run['mode'],
                'input_sha256': run['input_snapshot_sha256'], 'independent_plan_checks': checks,
                'full_run_reproduced': True, 'replanning_reproduced': True,
                'replanning_valid': replanned['validation']['valid'],
                'approval_status': replanned['approval_status'], 'figures': figures,
                'presentation_runtime': presentation_runtime,
                'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(sources)},
                'comparison': run['comparison'],
                'files_sha256': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'manifest.json'}}
    write_json(output / 'manifest.json', manifest)
    print(json.dumps({'output': str(output.resolve()), 'initial': run['initial']['objective'],
                      'ga': run['ga']['objective'], 'generations': run['generations_completed'],
                      'completed_at_checkpoint': replanned['completed_task_ids'],
                      'locked_unfinished': replanned['locked_unfinished_task_ids'],
                      'replan_unassigned': replanned['combined']['unassigned_task_ids'],
                      'figures': len(figures)}, ensure_ascii=False))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs' / 'portfolio')
    parser.add_argument('--no-figures', action='store_true')
    args = parser.parse_args()
    build(args.output_dir, args.seed, not args.no_figures)
