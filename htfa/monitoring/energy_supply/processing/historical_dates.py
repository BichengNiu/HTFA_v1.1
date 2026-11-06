"""Nearest source-day selection, with an earlier-day tie break."""
from datetime import date

from htfa.monitoring.energy_supply.processing.monitoring_cards import (
    SEA_MONITORING_AREAS,
    number,
)


def nearest_day(days, selected):
    candidates = {day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
                  for day in days if day is not None}
    return min(candidates, key=lambda day: (abs((day-selected).days), day), default=None)


def nearest_sea_day(rows, selected):
    coverage = {sea: {row['date'] for row in rows if row.get('sea') == sea
                      and number(row.get('passages')) is not None}
                for sea in SEA_MONITORING_AREAS}
    return nearest_day(set.intersection(*coverage.values()), selected)
