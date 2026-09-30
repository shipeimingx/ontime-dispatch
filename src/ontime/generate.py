"""Seeded illustrative inputs, not research experiments or measured factory data."""

import copy
import math
import random

from .export import write_json
from .input import validate_problem
from .models import UNITS


def synthetic_cases(seed=2026):
    rng = random.Random(seed)
    stations = [f'S{i:02d}' for i in range(1, 9)]
    points = {'DEPOT': (0, 0), **{key: (rng.randint(20, 180), rng.randint(20, 180))
                                for key in stations}}
    distance, travel = {}, {}
    for kind, speed in (('UAV', 8.0), ('AGV', 1.5)):
        distance[kind], travel[kind] = {}, {}
        for start, (x1, y1) in points.items():
            distance[kind][start], travel[kind][start] = {}, {}
            for end, (x2, y2) in points.items():
                length = (math.hypot(x1 - x2, y1 - y2) if kind == 'UAV'
                          else 1.2 * (abs(x1 - x2) + abs(y1 - y2)))
                # Distances are rounded illustrative inputs, then seconds are rounded up.
                length = round(length, 3)
                distance[kind][start][end] = length
                travel[kind][start][end] = math.ceil(length / speed)
    vehicles = []
    for kind, capacities, speed in (('UAV', (4, 6), 8.0), ('AGV', (35, 50), 1.5)):
        for number, capacity in enumerate(capacities, 1):
            vehicles.append({
                'id': f'{kind}-{number:02d}', 'type': kind, 'available': True,
                'capacity_kg': capacity, 'speed_m_s': speed,
                'trip_limit_s': 800 if kind == 'UAV' else 2000,
                'available_from_s': 0, 'available_until_s': 3600 if kind == 'UAV' else 7200,
                'load_s': 20 if kind == 'UAV' else 30,
                'depot_unload_s': 10 if kind == 'UAV' else 20,
                'turnaround_s': 60 if kind == 'UAV' else 45,
            })
    tasks = []
    for index, station in enumerate(stations):
        types = ['UAV'] if index % 2 == 0 else ['AGV']
        if index == 7:
            types = ['UAV', 'AGV']
        demand = round(rng.uniform(1, 3), 2) if 'UAV' in types else rng.randint(10, 25)
        earliest = rng.randint(0, 60)
        tasks.append({'id': f'T{index + 1:02d}', 'station_id': station, 'demand_kg': demand,
                      'earliest_s': earliest, 'latest_s': 500 + index * 180,
                      'unload_s': rng.randint(5, 15), 'service_s': rng.randint(10, 30),
                      'eligible_types': types, 'lateness_cost_per_s': rng.choice((1, 2, 4))})
    normal = {'schema_version': 2, 'scenario_label': 'Illustrative data — seeded synthetic normal',
              'units': dict(UNITS), 'window_mode': 'soft', 'depot_id': 'DEPOT',
              'stations': stations, 'vehicles': vehicles, 'tasks': tasks,
              'travel_time_s': travel, 'distance_m': distance,
              'metadata': {'generation_seed': seed, 'generator_version': 'synthetic_v1',
                           'coordinates_m': {key: list(point) for key, point in points.items()},
                           'assumptions_document': 'docs/scenarios.md',
                           'travel_source': 'UAV Euclidean; AGV 1.2 * Manhattan; ceil(m / representative m/s). No obstacle planner.'}}
    cases = {'normal': normal}
    overload = copy.deepcopy(normal)
    overload['scenario_label'] = 'Illustrative data — overload T08'
    overload['tasks'][7]['demand_kg'] = 60
    overload['metadata']['change'] = 'T08 60 kg exceeds maximum available capacity 50 kg.'
    cases['overload'] = overload
    conflict = copy.deepcopy(normal)
    conflict['scenario_label'] = 'Illustrative data — time-window conflict T01'
    conflict['tasks'][0].update(earliest_s=0, latest_s=1)
    conflict['metadata']['change'] = 'T01 service-start window [0,1] s; earliest loaded departure is 20 s.'
    cases['window_conflict'] = conflict
    unavailable = copy.deepcopy(normal)
    unavailable['scenario_label'] = 'Illustrative data — both UAVs unavailable'
    for vehicle in unavailable['vehicles']:
        if vehicle['type'] == 'UAV':
            vehicle['available'] = False
    unavailable['metadata']['change'] = 'UAV-01 and UAV-02 available=false; compatibility is not relaxed.'
    cases['unavailable'] = unavailable
    for value in cases.values():
        validate_problem(value)
    return cases


def generate_files(directory, seed=2026):
    from pathlib import Path
    directory = Path(directory)
    cases = synthetic_cases(seed)
    for name, problem in cases.items():
        write_json(directory / f'{name}.json', problem)
    return sorted(cases)
