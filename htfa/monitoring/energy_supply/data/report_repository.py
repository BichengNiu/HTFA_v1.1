"""Bounded reads of persisted observations for workbook publication."""

from __future__ import annotations

import json


def node_catalogs(connection):
    return {
        (kind, identifier): json.loads(payload)
        for kind, identifier, payload in connection.execute(
            "SELECT kind,id,payload FROM energy_supply.catalogs "
            "WHERE kind IN ('ports','chokepoints')",
        ).fetchall()
    }


def daily_observations(connection, kind):
    """Stream source facts without materializing the complete history."""
    cursor = connection.execute(
        "SELECT day,node_id,payload FROM energy_supply.portwatch_daily WHERE kind=?",
        [kind],
    )
    while batch := cursor.fetchmany(2000):
        for day, node, payload in batch:
            yield day, node, json.loads(payload)


def monthly_observed_vessels(connection):
    return connection.execute("""
        SELECT last_day(CAST(observed AT TIME ZONE 'UTC' AS DATE)),
               coalesce(json_extract_string(payload,'$.region'),'未知水域'),
               count(DISTINCT mmsi)
        FROM energy_supply.ais_reports GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
