"""Automated Ironbound and Unbound dynasty power rankings."""

__version__ = "2.0.0"

# `forecast` historically owns all forward-looking public helpers.  Keep that
# import surface stable while the weekly line/total model lives in its own
# focused module instead of enlarging the season/playoff simulator.
from . import forecast as _forecast
from .weekly_forecast import (
    attach_remaining_schedule_strength,
    attach_weekly_matchup_forecast,
    projection_fantasy_points,
)

_forecast.attach_remaining_schedule_strength = attach_remaining_schedule_strength
_forecast.attach_weekly_matchup_forecast = attach_weekly_matchup_forecast
_forecast.projection_fantasy_points = projection_fantasy_points
