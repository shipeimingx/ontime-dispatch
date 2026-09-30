"""Typed records for the 2026 illustrative model. All time fields are seconds."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Task:
    id: str
    station_id: str
    demand_kg: float
    earliest_s: int
    latest_s: int
    unload_s: int
    service_s: int
    eligible_types: tuple[str, ...]
    eligible_vehicle_ids: tuple[str, ...] | None = None
    lateness_cost_per_s: float = 1.0


@dataclass(frozen=True)
class Vehicle:
    id: str
    type: str
    available: bool
    capacity_kg: float
    trip_limit_s: int
    available_from_s: int
    available_until_s: int
    load_s: int
    depot_unload_s: int
    turnaround_s: int
    speed_m_s: float | None = None  # Legacy v1 input did not contain speed.


@dataclass(frozen=True)
class Problem:
    schema_version: int
    scenario_label: str
    depot_id: str
    stations: tuple[str, ...]
    vehicles: tuple[Vehicle, ...]
    tasks: tuple[Task, ...]
    travel_time_s: dict[str, dict[str, dict[str, int | None]]]
    distance_m: dict[str, dict[str, dict[str, float | None]]] | None = None
    window_mode: str = 'soft'
    units: dict[str, str] = field(default_factory=lambda: dict(UNITS))
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value):
        tasks = []
        for item in value['tasks']:
            data = dict(item)
            data['eligible_types'] = tuple(data['eligible_types'])
            if 'eligible_vehicle_ids' in data:
                data['eligible_vehicle_ids'] = tuple(data['eligible_vehicle_ids'])
            tasks.append(Task(**data))
        data = dict(value)
        data['tasks'] = tuple(tasks)
        data['vehicles'] = tuple(Vehicle(**v) for v in value['vehicles'])
        data['stations'] = tuple(value['stations'])
        return cls(**data)


UNITS = {'mass': 'kg', 'distance': 'm', 'time': 's', 'speed': 'm/s', 'cost': 'penalty_unit'}


@dataclass(frozen=True)
class Trip:
    trip_id: str
    vehicle_id: str
    task_ids: tuple[str, ...]
    load_start_s: int

    def to_dict(self):
        return {**asdict(self), 'task_ids': list(self.task_ids)}


@dataclass(frozen=True)
class Check:
    code: str
    passed: bool
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {'code': self.code, 'passed': self.passed, **self.evidence}


@dataclass(frozen=True)
class TravelLeg:
    from_node: str
    to_node: str
    start_s: int
    end_s: int
    travel_s: int
    distance_m: float | None

    def to_dict(self):
        data = asdict(self)
        data['from'], data['to'] = data.pop('from_node'), data.pop('to_node')
        return data


@dataclass(frozen=True)
class ScheduledStop:
    task_id: str
    station_id: str
    arrival_s: int
    earliest_s: int
    latest_s: int
    waiting_s: int
    service_start_s: int
    unload_s: int
    unload_end_s: int
    service_s: int
    completion_s: int
    lateness_s: int
    lateness_cost_per_s: float
    lateness_cost: float
    remaining_payload_kg: float
    demand_kg: float
    status: str = 'planned'


@dataclass(frozen=True)
class CandidateAttempt:
    vehicle_id: str
    candidate_kind: str
    candidate_task_ids: tuple[str, ...]
    failed_checks: tuple[Check, ...]
    insertion_position: int | None = None

    def to_dict(self):
        return {'vehicle_id': self.vehicle_id, 'candidate_kind': self.candidate_kind,
                'candidate_task_ids': list(self.candidate_task_ids),
                'insertion_position': self.insertion_position,
                'failed_checks': [c.to_dict() for c in self.failed_checks]}


@dataclass(frozen=True)
class UnassignedTask:
    task_id: str
    reason_code: str
    explanation: str
    reason_codes: tuple[str, ...] = ()
    attempts: tuple[CandidateAttempt, ...] = ()

    def to_dict(self):
        return {'task_id': self.task_id, 'reason_code': self.reason_code,
                'reason_codes': list(self.reason_codes), 'explanation': self.explanation,
                'attempts': [a.to_dict() for a in self.attempts]}


@dataclass(frozen=True)
class Plan:
    trips: tuple[Trip, ...]
    unassigned: tuple[UnassignedTask, ...]
    mode: str = 'soft'
    seed: int = 0

    def to_dict(self):
        return {'trips': [t.to_dict() for t in self.trips],
                'unassigned': [t.to_dict() for t in self.unassigned]}


@dataclass
class TripEvaluation:
    trip: Trip
    vehicle_type: str
    speed_m_s: float | None
    route: tuple[str, ...]
    payload_kg: float
    capacity_kg: float
    departure_s: int
    depot_wait_s: int
    load_s: int
    depot_unload_s: int
    turnaround_s: int
    stops: list[ScheduledStop] = field(default_factory=list)
    legs: list[TravelLeg] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    return_s: int | None = None
    mission_s: int | None = None
    depot_unload_end_s: int | None = None
    next_ready_s: int | None = None
    turnaround_applied: bool = False

    @property
    def valid(self):
        return self.return_s is not None and all(c.passed for c in self.checks)

    @property
    def travel_s(self):
        return sum(leg.travel_s for leg in self.legs)

    @property
    def lateness_cost(self):
        return sum(stop.lateness_cost for stop in self.stops)

    def to_dict(self):
        lengths = [leg.distance_m for leg in self.legs]
        return {**self.trip.to_dict(), 'type': self.vehicle_type, 'speed_m_s': self.speed_m_s,
                'route': list(self.route), 'payload_kg': self.payload_kg, 'capacity_kg': self.capacity_kg,
                'departure_s': self.departure_s, 'depot_wait_s': self.depot_wait_s,
                'load_s': self.load_s, 'depot_unload_s': self.depot_unload_s,
                'turnaround_s': self.turnaround_s, 'return_s': self.return_s,
                'mission_s': self.mission_s, 'depot_unload_end_s': self.depot_unload_end_s,
                'next_ready_s': self.next_ready_s, 'turnaround_applied': self.turnaround_applied,
                'planned_end_s': self.next_ready_s if self.turnaround_applied else self.depot_unload_end_s,
                'valid': self.valid, 'stops': [asdict(s) for s in self.stops],
                'legs': [leg.to_dict() for leg in self.legs], 'checks': [c.to_dict() for c in self.checks],
                'travel_s': self.travel_s, 'waiting_s': sum(s.waiting_s for s in self.stops),
                'station_unload_s': sum(s.unload_s for s in self.stops),
                'service_s': sum(s.service_s for s in self.stops),
                'lateness_s': sum(s.lateness_s for s in self.stops),
                'lateness_cost': self.lateness_cost,
                'distance_m': sum(lengths) if lengths and all(d is not None for d in lengths) else None}


@dataclass
class Evaluation:
    plan: Plan
    trips: list[TripEvaluation]
    checks: list[Check]

    @property
    def valid(self):
        return all(t.valid for t in self.trips) and all(c.passed for c in self.checks)

    def to_dict(self):
        from . import PROFILE
        assigned = sorted({task for trip in self.plan.trips for task in trip.task_ids})
        unassigned = [item.task_id for item in self.plan.unassigned]
        trips = [trip.to_dict() for trip in self.trips]
        return {'profile': PROFILE, 'window_event': 'service_start', 'mode': self.plan.mode,
                'seed': self.plan.seed, 'units': dict(UNITS), 'valid': self.valid,
                'complete': self.valid and not unassigned,
                'coverage': 'Complete' if not unassigned else ('Partial' if assigned else 'No assignment'),
                'assigned_task_ids': assigned, 'unassigned_task_ids': sorted(unassigned),
                'unassigned': [u.to_dict() for u in self.plan.unassigned],
                'trips': trips, 'checks': [c.to_dict() for c in self.checks],
                'summary': {'assigned_count': len(assigned), 'unassigned_count': len(unassigned),
                            'trip_count': len(trips), 'travel_s': sum(t['travel_s'] for t in trips),
                            'waiting_s': sum(t['waiting_s'] for t in trips),
                            'lateness_s': sum(t['lateness_s'] for t in trips),
                            'lateness_cost': sum(t['lateness_cost'] for t in trips)},
                'plan_input': self.plan.to_dict(), 'execution_status': 'candidate_only'}
