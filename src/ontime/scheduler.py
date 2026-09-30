"""Finite insertion heuristic. Every accepted candidate satisfies all hard checks."""

import random

from .evaluate import check_plan, check_trip
from .input import InputError, as_problem
from .models import CandidateAttempt, Plan, Trip, UnassignedTask


def _explain(task, vehicles, attempts):
    compatible = [v for v in vehicles if v.type in task.eligible_types and
                  (task.eligible_vehicle_ids is None or v.id in task.eligible_vehicle_ids)]
    available = [v for v in compatible if v.available]
    capacity_ok = [v for v in available if v.capacity_kg >= task.demand_kg]
    relevant = [a for a in attempts if a.vehicle_id in {v.id for v in capacity_ok}]
    codes = tuple(sorted({c.code for a in attempts for c in a.failed_checks}))
    if not vehicles:
        reason, text = 'no_vehicles', 'No devices configured.'
    elif not compatible:
        reason, text = 'no_compatible_vehicle', 'No device matches task type/ID eligibility.'
    elif not available:
        reason, text = 'device_unavailable', 'All compatible devices are unavailable.'
    elif not capacity_ok:
        reason, text = 'payload_exceeded', 'Task alone exceeds every available compatible device capacity.'
    elif relevant and all(any(c.code == 'time_window' for c in a.failed_checks) for a in relevant):
        reason, text = 'time_window_conflict', 'Every tested capacity-compatible candidate violates a hard service-start window.'
    elif relevant and all(any(c.code == 'trip_limit' for c in a.failed_checks) for a in relevant):
        reason, text = 'endurance_exceeded', 'Every tested capacity-compatible candidate exceeds the full depot-return mission limit.'
    elif relevant and all(any(c.code == 'availability_end' for c in a.failed_checks) for a in relevant):
        reason, text = 'availability_exceeded', 'Every tested capacity-compatible candidate finishes depot unloading after availability.'
    elif relevant and all(any(c.code == 'route_edge' for c in a.failed_checks) for a in relevant):
        reason, text = 'route_unavailable', 'Every tested capacity-compatible candidate contains a forbidden travel edge.'
    else:
        reason, text = 'no_feasible_candidate_found', 'No feasible candidate in this bounded insertion/new-trip search.'
    return UnassignedTask(task.id, reason, text + ' Search is not a global infeasibility proof.',
                          codes, tuple(attempts))


def urgency_order(problem):
    """The actual first-stage construction order, also the seed chromosome."""
    problem = as_problem(problem)
    return tuple(t.id for t in sorted(problem.tasks,
                 key=lambda t: (t.latest_s, t.latest_s - t.earliest_s, t.earliest_s, t.id)))


def construct_plan(problem, mode=None, seed=0, task_order=None):
    problem = as_problem(problem)
    mode = mode or problem.window_mode
    if mode not in ('soft', 'hard'):
        raise InputError('mode: expected soft or hard')
    if type(seed) is not int:
        raise InputError('seed: expected integer')
    rng = random.Random(seed)  # Used only after all substantive candidate priorities tie.
    vehicles = sorted(problem.vehicles, key=lambda v: v.id)
    routes = {v.id: [] for v in vehicles}
    unassigned = []
    ids = urgency_order(problem) if task_order is None else tuple(task_order)
    tasks = {t.id: t for t in problem.tasks}
    if (any(not isinstance(key, str) for key in ids) or
            len(ids) != len(tasks) or len(set(ids)) != len(ids) or set(ids) != set(tasks)):
        raise InputError('task_order: expected a permutation of all task IDs, exactly once')
    ordered = [tasks[key] for key in ids]  # Explicit orders are never sorted again.
    for task in ordered:
        candidates, evidence = [], []
        for vehicle in vehicles:
            trips = routes[vehicle.id]
            ready = trips[-1].next_ready_s if trips else vehicle.available_from_s
            attempts = []
            if trips:
                old = trips[-1]
                before_last = trips[-2].next_ready_s if len(trips) > 1 else vehicle.available_from_s
                for position in range(len(old.trip.task_ids) + 1):
                    ids = (*old.trip.task_ids[:position], task.id, *old.trip.task_ids[position:])
                    attempts.append((False, Trip(old.trip.trip_id, vehicle.id, ids, old.trip.load_start_s),
                                     before_last, old, position))
            attempts.append((True, Trip(f'{vehicle.id}-trip-{len(trips) + 1}', vehicle.id,
                                       (task.id,), ready), ready, None, None))
            for new_trip, trip, required_ready, old, position in attempts:
                evaluated = check_trip(problem, vehicle, trip, mode, required_ready)
                if evaluated.valid:
                    stop = next(s for s in evaluated.stops if s.task_id == task.id)
                    score = (evaluated.lateness_cost - (old.lateness_cost if old else 0),
                             evaluated.travel_s - (old.travel_s if old else 0),
                             stop.service_start_s, new_trip, rng.random())
                    candidates.append((score, vehicle.id, new_trip, evaluated))
                else:
                    evidence.append(CandidateAttempt(
                        vehicle.id, 'new_trip' if new_trip else 'insert_current_trip', trip.task_ids,
                        tuple(c for c in evaluated.checks if not c.passed), position))
        if not candidates:
            unassigned.append(_explain(task, vehicles, evidence))
            continue  # No retry loop: move once to the next task.
        _, vehicle_id, new_trip, evaluated = min(candidates, key=lambda item: item[0])
        if new_trip:
            routes[vehicle_id].append(evaluated)
        else:
            routes[vehicle_id][-1] = evaluated
    plan = Plan(tuple(t.trip for v in vehicles for t in routes[v.id]), tuple(unassigned), mode, seed)
    if not check_plan(problem, plan).valid:
        raise RuntimeError('Constructed plan failed independent validation')
    return plan


def schedule(problem, mode=None, seed=0):
    problem = as_problem(problem)
    plan = construct_plan(problem, mode, seed)
    result = check_plan(problem, plan).to_dict()
    result.update(scenario_label=problem.scenario_label, algorithm='urgency_insertion_v2',
                  search_exhaustive=False)
    return result
