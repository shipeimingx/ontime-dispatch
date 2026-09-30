"""2026 new two-stage permutation GA; no claims of research reproduction."""

from dataclasses import asdict, dataclass, field
from fractions import Fraction
import hashlib
import json
import math
import random

from .evaluate import check_plan
from .input import InputError, as_problem, number, problem_to_dict
from .models import Plan
from .scheduler import construct_plan, urgency_order

METHOD_PROFILE = 'two-stage-permutation-ga-2026-v1'


@dataclass(frozen=True)
class CostParameters:
    uav_transport_per_s: float = 0.02
    agv_transport_per_s: float = 0.01
    lateness_multiplier: float = 1.0

    def validate(self):
        for name in ('uav_transport_per_s', 'agv_transport_per_s'):
            number(getattr(self, name), name, 'penalty_unit/s')
        number(self.lateness_multiplier, 'lateness_multiplier', 'dimensionless')

    def to_dict(self):
        return {**asdict(self), 'transport_coefficient_unit': 'penalty_unit/s',
                'task_lateness_coefficient_unit': 'penalty_unit/s',
                'lateness_multiplier_unit': 'dimensionless', 'cost_unit': 'penalty_unit',
                'transport_basis': 'travel seconds on all legs, including depot return',
                'objective_priority': ['unassigned_count', 'transport_cost + lateness_penalty'],
                'illustrative_coefficients': True}


@dataclass(frozen=True)
class GAParameters:
    population_size: int = 24
    max_generations: int = 40
    elite_count: int = 2
    tournament_size: int = 3
    crossover_rate: float = 0.9
    mutation_rate: float = 0.25
    patience: int = 12  # 0 disables stagnation stopping.
    seed: int = 2026

    def validate(self):
        for name in ('population_size', 'max_generations', 'elite_count',
                     'tournament_size', 'patience', 'seed'):
            if type(getattr(self, name)) is not int:
                raise InputError(f'{name}: expected integer')
        if self.population_size < 2 or self.max_generations < 0 or self.patience < 0:
            raise InputError('population_size >= 2; max_generations and patience >= 0')
        if not 1 <= self.elite_count < self.population_size:
            raise InputError('elite_count: expected 1 <= elites < population_size')
        if not 1 <= self.tournament_size <= self.population_size:
            raise InputError('tournament_size: expected 1 <= size <= population_size')
        for name in ('crossover_rate', 'mutation_rate'):
            number(getattr(self, name), name, 'probability')
            if getattr(self, name) > 1:
                raise InputError(f'{name}: expected <= 1')


@dataclass(frozen=True, order=True)
class Objective:
    unassigned_count: int
    total_cost: Fraction
    transport_cost: Fraction = field(compare=False)
    lateness_penalty: Fraction = field(compare=False)

    def to_dict(self):
        values = {'unassigned_count': self.unassigned_count,
                  'total_cost': float(self.total_cost), 'transport_cost': float(self.transport_cost),
                  'lateness_penalty': float(self.lateness_penalty), 'cost_unit': 'penalty_unit'}
        if not all(math.isfinite(values[k]) for k in ('total_cost', 'transport_cost', 'lateness_penalty')):
            raise InputError('Objective exceeds finite numeric output range')
        return values


@dataclass(frozen=True)
class Individual:
    chromosome: tuple[str, ...]
    plan: Plan
    objective: Objective


def objective_from_evaluation(problem, evaluated, costs):
    if not evaluated.valid:
        raise InputError('Invalid plans cannot enter GA fitness comparison')
    costs.validate()
    coefficients = {'UAV': Fraction(str(costs.uav_transport_per_s)),
                    'AGV': Fraction(str(costs.agv_transport_per_s))}
    transport = sum((coefficients[t.vehicle_type] * t.travel_s for t in evaluated.trips), Fraction(0))
    weights = {t.id: Fraction(str(t.lateness_cost_per_s)) for t in problem.tasks}
    late = sum((weights[s.task_id] * s.lateness_s for t in evaluated.trips for s in t.stops), Fraction(0))
    penalty = Fraction(str(costs.lateness_multiplier)) * late
    value = Objective(len(evaluated.plan.unassigned), transport + penalty, transport, penalty)
    value.to_dict()  # Reject overflow before comparisons or export.
    return value


def decode_chromosome(problem, chromosome, mode=None, decoder_seed=2026):
    """Chromosome is task consideration order, not necessarily final stop order."""
    if not isinstance(chromosome, (tuple, list)):
        raise InputError('chromosome: expected a task-ID permutation array')
    plan = construct_plan(problem, mode, decoder_seed, task_order=chromosome)
    if not check_plan(problem, plan).valid:
        raise RuntimeError('Decoded plan failed independent validation')
    return plan


def order_crossover(first, second, rng):
    """OX: copy a segment, fill other slots in the second parent's cyclic order."""
    if len(first) != len(second) or len(set(first)) != len(first) or set(first) != set(second):
        raise InputError('OX parents must be permutations of the same unique IDs')
    size = len(first)
    if size < 2:
        return tuple(first)
    start, end = sorted(rng.sample(range(size + 1), 2))
    child = [None] * size
    child[start:end] = first[start:end]
    retained = set(first[start:end])
    remaining = [second[i % size] for i in range(end, end + size) if second[i % size] not in retained]
    positions = [i % size for i in range(end, end + size) if child[i % size] is None]
    for position, gene in zip(positions, remaining):
        child[position] = gene
    return tuple(child)


def mutate(chromosome, rng, kind=None):
    if kind not in (None, 'swap', 'insert'):
        raise InputError('mutation kind: expected swap or insert')
    if len(chromosome) < 2:
        return tuple(chromosome)
    genes = list(chromosome)
    first, second = rng.sample(range(len(genes)), 2)
    kind = kind or rng.choice(('swap', 'insert'))
    if kind == 'swap':
        genes[first], genes[second] = genes[second], genes[first]
    else:
        genes.insert(second, genes.pop(first))
    return tuple(genes)


def _plan_result(problem, individual, costs, algorithm):
    evaluated = check_plan(problem, individual.plan)  # Recompute both final exported plans.
    objective = objective_from_evaluation(problem, evaluated, costs)
    if objective != individual.objective:
        raise RuntimeError('Recomputed objective differs from stored GA objective')
    result = evaluated.to_dict()
    result.update(scenario_label=problem.scenario_label, method_profile=METHOD_PROFILE,
                  algorithm=algorithm, chromosome=list(individual.chromosome),
                  objective=objective.to_dict(), objective_parameters=costs.to_dict(),
                  search_exhaustive=False)
    for trip in result['trips']:
        rate = costs.uav_transport_per_s if trip['type'] == 'UAV' else costs.agv_transport_per_s
        trip['transport_cost_per_s'] = rate
        trip['transport_cost'] = float(Fraction(str(rate)) * trip['travel_s'])
        for stop in trip['stops']:
            stop['objective_lateness_penalty'] = float(Fraction(str(costs.lateness_multiplier)) *
                Fraction(str(stop['lateness_cost_per_s'])) * stop['lateness_s'])
    result['summary'].update(transport_cost=float(objective.transport_cost),
                             lateness_penalty=float(objective.lateness_penalty),
                             total_cost=float(objective.total_cost))
    return result


def _compare(initial, final):
    metrics = ('assigned_count', 'unassigned_count', 'trip_count', 'travel_s', 'waiting_s',
               'lateness_s', 'lateness_cost')
    rows = [{'metric': key, 'initial': initial['summary'][key], 'ga': final['summary'][key],
             'delta_ga_minus_initial': final['summary'][key] - initial['summary'][key],
             'unit': 's' if key.endswith('_s') else ('penalty_unit' if key.endswith('cost') else 'count')}
            for key in metrics]
    for key in ('transport_cost', 'lateness_penalty', 'total_cost'):
        rows.append({'metric': key, 'initial': initial['objective'][key], 'ga': final['objective'][key],
                     'delta_ga_minus_initial': float(Fraction(str(final['objective'][key])) -
                                                      Fraction(str(initial['objective'][key]))),
                     'unit': 'penalty_unit'})
    def assignments(result):
        assigned = {s['task_id']: {'status': 'planned', 'vehicle_id': t['vehicle_id'],
                                  'trip_id': t['trip_id'], **s}
                    for t in result['trips'] for s in t['stops']}
        assigned.update({u['task_id']: {'status': 'unassigned', 'reason_code': u['reason_code']}
                         for u in result['unassigned']})
        return assigned
    before, after = assignments(initial), assignments(final)
    tasks = [{'task_id': key, 'initial': before[key], 'ga': after[key], 'changed': before[key] != after[key]}
             for key in sorted(before)]
    return {'metrics': rows, 'tasks': tasks}


def run_two_stage(problem, mode=None, parameters=None, costs=None):
    problem = as_problem(problem)
    parameters, costs = parameters or GAParameters(), costs or CostParameters()
    parameters.validate()
    costs.validate()
    mode = mode or problem.window_mode
    rng = random.Random(parameters.seed)
    seed_chromosome = urgency_order(problem)
    # Phase 1 actually runs the existing heuristic, not a reconstructed substitute.
    initial_plan = construct_plan(problem, mode, parameters.seed)
    initial_evaluation = check_plan(problem, initial_plan)
    initial = Individual(seed_chromosome, initial_plan,
                         objective_from_evaluation(problem, initial_evaluation, costs))
    cache, cache_hits = {}, 0

    def evaluate(chromosome):
        nonlocal cache_hits
        chromosome = tuple(chromosome)
        if chromosome in cache:
            cache_hits += 1
            return cache[chromosome]
        plan = decode_chromosome(problem, chromosome, mode, parameters.seed)
        evaluated = check_plan(problem, plan)
        individual = Individual(chromosome, plan, objective_from_evaluation(problem, evaluated, costs))
        cache[chromosome] = individual
        return individual

    decoded_seed = evaluate(seed_chromosome)
    if decoded_seed.plan != initial_plan or decoded_seed.objective != initial.objective:
        raise RuntimeError('First-stage seed does not round-trip through the deterministic decoder')
    population, population_record = [decoded_seed], []
    sources = ['heuristic_seed']
    for index in range(1, parameters.population_size):
        if index <= (parameters.population_size - 1) // 2:
            chromosome = seed_chromosome
            for _ in range(rng.randint(1, 3)):
                chromosome = mutate(chromosome, rng)
            source = 'perturbed_heuristic'
        else:
            genes = list(seed_chromosome)
            rng.shuffle(genes)
            chromosome, source = tuple(genes), 'random_permutation'
        population.append(evaluate(chromosome))
        sources.append(source)
    for index, individual in enumerate(population):
        population_record.append({'index': index, 'source': sources[index],
                                  'chromosome': list(individual.chromosome),
                                  'objective': individual.objective.to_dict(), 'independently_validated': True})
    best = initial  # Equal objectives keep the first-stage plan, including its provenance.
    best_generation, stagnant, iterations = 0, 0, []
    for candidate in population:
        if candidate.objective < best.objective:
            best = candidate

    def record(generation):
        generation_best = min(population, key=lambda i: i.objective)
        iterations.append({'generation': generation, 'generation_best': generation_best.objective.to_dict(),
                           'best_known': best.objective.to_dict(), 'best_chromosome': list(best.chromosome),
                           'population_unique': len({i.chromosome for i in population}),
                           'decoded_unique_total': len(cache), 'cache_hits_total': cache_hits,
                           'stagnant_generations': stagnant})

    record(0)
    stop_reason = 'max_generations'
    if len(seed_chromosome) < 2:
        stop_reason = 'permutation_space_trivial'
    else:
        for generation in range(1, parameters.max_generations + 1):
            ranked = sorted(population, key=lambda i: i.objective)
            # Explicit best-known archive member survives even objective ties.
            offspring = [best, *ranked[:parameters.elite_count - 1]]
            def select():
                return min(rng.sample(population, parameters.tournament_size), key=lambda i: i.objective)
            while len(offspring) < parameters.population_size:
                first, second = select(), select()
                chromosome = (order_crossover(first.chromosome, second.chromosome, rng)
                              if rng.random() < parameters.crossover_rate else first.chromosome)
                if rng.random() < parameters.mutation_rate:
                    chromosome = mutate(chromosome, rng)
                offspring.append(evaluate(chromosome))
            population = offspring
            generation_best = min(population, key=lambda i: i.objective)
            if generation_best.objective < best.objective:
                best, best_generation, stagnant = generation_best, generation, 0
            else:
                stagnant += 1
            record(generation)
            if parameters.patience and stagnant >= parameters.patience:
                stop_reason = 'stagnation_patience'
                break
    if best.objective > initial.objective:
        raise RuntimeError('GA lost the initial best-known plan')
    before = _plan_result(problem, initial, costs, 'urgency_insertion_v2')
    after = _plan_result(problem, best, costs, 'permutation_ga_2026_v1')
    comparison = _compare(before, after)
    improved = best.objective < initial.objective
    comparison.update(improved=improved, comparison_scope='this input, mode, parameters and fixed seed only',
                      initial_objective=initial.objective.to_dict(), ga_objective=best.objective.to_dict(),
                      conclusion='Strict lexicographic improvement in this run.' if improved
                      else 'No strict objective improvement; the first-stage plan was retained.')
    snapshot = problem_to_dict(problem)
    canonical_input = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                 separators=(',', ':')).encode('utf-8')
    return {'method_profile': METHOD_PROFILE, 'illustrative': True, 'mode': mode,
            'input_snapshot': snapshot, 'input_snapshot_sha256': hashlib.sha256(canonical_input).hexdigest(),
            'parameters': {**asdict(parameters), 'decoder_seed': parameters.seed,
                           'costs': costs.to_dict(), 'two_opt_implemented': False},
            'heuristic_seed': {'chromosome': list(seed_chromosome), 'population_index': 0,
                               'decoded_plan_matches_initial': True, 'objective': initial.objective.to_dict()},
            'initial_population': population_record, 'iterations': iterations,
            'generations_completed': iterations[-1]['generation'], 'best_found_generation': best_generation,
            'stop_reason': stop_reason, 'initial': before, 'ga': after, 'comparison': comparison}
