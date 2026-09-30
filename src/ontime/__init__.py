"""OnTime Dispatch: a new 2026 illustrative scheduling implementation."""

PROFILE = "python-demo-2026-v2"

from .models import Evaluation, Plan, Problem, ScheduledStop, Task, Trip, Vehicle

__all__ = ['PROFILE', 'Task', 'Vehicle', 'Trip', 'ScheduledStop', 'Plan', 'Evaluation', 'Problem']
