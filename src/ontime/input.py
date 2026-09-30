"""Strict, dependency-free input checks. Feasibility is checked separately."""

import json
import math
from pathlib import Path

from .models import Problem, UNITS


class InputError(ValueError):
    pass


def fields(value, required, optional, path):
    if not isinstance(value, dict):
        raise InputError(f"{path}: expected object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise InputError(f"{path}: missing={sorted(missing)}, unknown={sorted(extra)}")


def seconds(value, path, minimum=0):
    if type(value) is not int or value < minimum:
        raise InputError(f"{path}: expected integer seconds >= {minimum}")


def mass(value, path):
    number(value, path, 'kg', positive=True)


def number(value, path, unit, positive=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or value < 0 or (positive and value == 0):
        raise InputError(f"{path}: expected finite {unit} {'> 0' if positive else '>= 0'}")


def identifier(value, path):
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{path}: expected nonempty string")


def string_list(value, path, allowed=None, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value):
        raise InputError(f"{path}: expected {'nonempty ' if nonempty else ''}array")
    for item in value:
        identifier(item, path)
    if len(set(value)) != len(value):
        raise InputError(f"{path}: duplicate values")
    if allowed is not None and not set(value) <= set(allowed):
        raise InputError(f"{path}: unknown values {sorted(set(value) - set(allowed))}")


def object_list(value, path):
    if not isinstance(value, list):
        raise InputError(f"{path}: expected array")
    for item in value:
        if not isinstance(item, dict):
            raise InputError(f"{path}: expected object entries")


def unique_ids(items, path):
    ids = [item['id'] for item in items]
    if len(set(ids)) != len(ids):
        raise InputError(f"{path}: duplicate ids")


def matrix(value, nodes, path, distance=False):
    fields(value, ('UAV', 'AGV'), (), path)
    for kind, rows in value.items():
        fields(rows, nodes, (), f"{path}.{kind}")
        for start, row in rows.items():
            fields(row, nodes, (), f"{path}.{kind}.{start}")
            for end, value in row.items():
                cell = f"{path}.{kind}.{start}.{end}"
                if value is not None:
                    if distance:
                        number(value, cell, 'm')
                    else:
                        seconds(value, cell)
                if start == end and value != 0:
                    raise InputError(f"{cell}: diagonal must be 0")


def validate_problem(problem):
    fields(problem, ('schema_version', 'scenario_label', 'depot_id', 'stations',
                     'vehicles', 'tasks', 'travel_time_s'),
           ('window_mode', 'distance_m', 'units', 'metadata'), 'input')
    if type(problem['schema_version']) is not int or problem['schema_version'] not in (1, 2):
        raise InputError('schema_version: expected 1 or 2')
    if problem['schema_version'] == 2 and 'units' not in problem:
        raise InputError('units: schema v2 requires explicit kg/m/s/m/s/penalty_unit labels')
    if 'units' in problem and problem['units'] != UNITS:
        raise InputError(f'units: expected {UNITS}; no implicit unit conversion')
    if 'metadata' in problem and not isinstance(problem['metadata'], dict):
        raise InputError('metadata: expected descriptive object (not scheduling rules)')
    identifier(problem['scenario_label'], 'scenario_label')
    identifier(problem['depot_id'], 'depot_id')
    string_list(problem['stations'], 'stations')
    if problem['depot_id'] in problem['stations']:
        raise InputError('stations: depot must not be a station')
    if problem.get('window_mode', 'soft') not in ('soft', 'hard'):
        raise InputError('window_mode: expected soft or hard')
    object_list(problem['vehicles'], 'vehicles')
    for vehicle in problem['vehicles']:
        fields(vehicle, ('id', 'type', 'available', 'capacity_kg', 'trip_limit_s',
                         'available_from_s', 'available_until_s', 'load_s',
                         'depot_unload_s', 'turnaround_s'), ('speed_m_s',), 'vehicle')
        identifier(vehicle['id'], 'vehicle.id')
        if vehicle['type'] not in ('UAV', 'AGV'):
            raise InputError('vehicle.type: expected UAV or AGV')
        if type(vehicle['available']) is not bool:
            raise InputError('vehicle.available: expected boolean')
        mass(vehicle['capacity_kg'], 'vehicle.capacity_kg')
        if problem['schema_version'] == 2 and 'speed_m_s' not in vehicle:
            raise InputError('vehicle.speed_m_s: required in schema v2')
        if 'speed_m_s' in vehicle:
            number(vehicle['speed_m_s'], 'vehicle.speed_m_s', 'm/s', positive=True)
        for key in ('trip_limit_s', 'available_from_s', 'available_until_s',
                    'load_s', 'depot_unload_s', 'turnaround_s'):
            seconds(vehicle[key], f'vehicle.{key}', 1 if key == 'trip_limit_s' else 0)
        if vehicle['available_until_s'] < vehicle['available_from_s']:
            raise InputError('vehicle: availability end precedes start')
    unique_ids(problem['vehicles'], 'vehicles')
    object_list(problem['tasks'], 'tasks')
    vehicle_ids = [vehicle['id'] for vehicle in problem['vehicles']]
    for task in problem['tasks']:
        fields(task, ('id', 'station_id', 'demand_kg', 'earliest_s', 'latest_s',
                      'unload_s', 'service_s', 'eligible_types'),
               ('eligible_vehicle_ids', 'lateness_cost_per_s'), 'task')
        identifier(task['id'], 'task.id')
        identifier(task['station_id'], 'task.station_id')
        if task['station_id'] not in problem['stations']:
            raise InputError('task.station_id: unknown station')
        mass(task['demand_kg'], 'task.demand_kg')
        if problem['schema_version'] == 2 and 'lateness_cost_per_s' not in task:
            raise InputError('task.lateness_cost_per_s: required in schema v2')
        if 'lateness_cost_per_s' in task:
            number(task['lateness_cost_per_s'], 'task.lateness_cost_per_s', 'penalty_unit/s')
        for key in ('earliest_s', 'latest_s', 'unload_s', 'service_s'):
            seconds(task[key], f'task.{key}')
        if task['latest_s'] < task['earliest_s']:
            raise InputError('task: window end precedes start')
        string_list(task['eligible_types'], 'task.eligible_types', ('UAV', 'AGV'))
        if 'eligible_vehicle_ids' in task:
            string_list(task['eligible_vehicle_ids'], 'task.eligible_vehicle_ids', vehicle_ids)
    unique_ids(problem['tasks'], 'tasks')
    nodes = [problem['depot_id'], *problem['stations']]
    matrix(problem['travel_time_s'], nodes, 'travel_time_s')
    if 'distance_m' in problem:
        matrix(problem['distance_m'], nodes, 'distance_m', distance=True)
    return problem


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f'JSON: duplicate key {key}')
        result[key] = value
    return result


def read_json(path):
    def reject_constant(value):
        raise InputError(f'JSON: invalid constant {value}')
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'),
                          object_pairs_hook=_pairs, parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(str(exc)) from exc


def load_problem(path):
    return validate_problem(read_json(path))


def problem_to_dict(value):
    """Serializable normalized snapshot, including declared v1 default assumptions."""
    from dataclasses import asdict
    data = asdict(value)
    data['stations'] = list(value.stations)
    data['tasks'] = list(data['tasks'])
    data['vehicles'] = list(data['vehicles'])
    for task in data['tasks']:
        task['eligible_types'] = list(task['eligible_types'])
        if task['eligible_vehicle_ids'] is None:
            del task['eligible_vehicle_ids']
        else:
            task['eligible_vehicle_ids'] = list(task['eligible_vehicle_ids'])
    for vehicle in data['vehicles']:
        if vehicle['speed_m_s'] is None:
            del vehicle['speed_m_s']
    if data['distance_m'] is None:
        del data['distance_m']
    return data


def as_problem(value):
    """Validate typed inputs too, so library calls cannot bypass unit checks."""
    if isinstance(value, Problem):
        value = problem_to_dict(value)
    return Problem.from_dict(validate_problem(value))


def load_instance(path):
    return Problem.from_dict(load_problem(path))
