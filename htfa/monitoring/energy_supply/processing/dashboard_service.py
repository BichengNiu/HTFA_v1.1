"""Prepare the energy dashboard independently of Streamlit and session state."""

from htfa.monitoring.energy_supply.contracts import (
    DashboardContext,
    DashboardQuery,
    DashboardViewState,
)
from htfa.monitoring.energy_supply.data import storage as data_store
from htfa.monitoring.energy_supply.processing import ais as AIS
from htfa.monitoring.energy_supply.processing import catalogs, report_data
from htfa.monitoring.energy_supply.processing import portwatch as PORTWATCH
from htfa.monitoring.energy_supply.processing.dashboard_data import (
    collector_status,
    initialize_storage,
    load_chokepoints,
    load_ports,
    nearest_portwatch_day,
    openwaters_snapshot,
    portwatch_state,
    snapshot_date_bounds,
    vessel_tracks,
)


def load_context() -> DashboardContext:
    initialize_storage()
    versions = data_store.revisions(("ports", "chokepoints", "ais", "sea", "assets"))

    def local(kind, resource):
        return portwatch_state(kind, resource, PORTWATCH.MODULE_VERSION, versions[kind])

    ports, ports_error = local("ports", "catalog")
    chokepoints, chokes_error = local("chokepoints", "catalog")
    newest, ports_date_error = local("ports", "latest_date")
    newest_choke, chokes_date_error = local("chokepoints", "latest_date")
    first, last = snapshot_date_bounds(catalogs.snapshot_identity())
    return DashboardContext(
        catalogs.load_catalog("assets"),
        ports,
        chokepoints,
        newest,
        newest_choke,
        first,
        last,
        versions,
        ports_error or ports_date_error,
        chokes_error or chokes_date_error,
    )


def prepare_snapshot(
    context: DashboardContext, query: DashboardQuery
) -> DashboardViewState:
    assets, available_ports = context.assets, context.ports
    available_chokepoints = context.chokepoints
    newest_day, newest_chokepoint_day = (
        context.newest_day,
        context.newest_chokepoint_day,
    )
    revisions = display_revisions = context.revisions
    refresh_revision = "initial"
    snapshot_identity = catalogs.snapshot_identity()
    port_catalog_error, port_latest_error = context.port_error, None
    chokepoint_catalog_error, chokepoint_latest_error = context.chokepoint_error, None
    selected_day = (
        nearest_portwatch_day("ports", query.selected_day, snapshot_identity)
        if query.selected_day
        else newest_day
    )
    selected_chokepoint_day = (
        nearest_portwatch_day("chokepoints", query.selected_day, snapshot_identity)
        if query.selected_day
        else newest_chokepoint_day
    )
    selected_sea_day = (
        report_data.card_sea_history(
            display_revisions["sea"], query.selected_day.isoformat()
        ).get("selected_day")
        if query.selected_day
        else None
    )
    open_state = openwaters_snapshot(AIS.MODULE_VERSION, query.selected_day)
    live_positions = open_state.get("vessels", [])
    ais_status = collector_status()

    port_error = port_catalog_error or port_latest_error
    ports: list[dict] = []
    if selected_day is not None and available_ports:
        ports, activity_error, _ = load_ports(
            available_ports,
            selected_day,
            rolling_days=7,
            refresh_revision=refresh_revision,
            stored_revision=revisions["ports"],
        )
        port_error = (
            "；".join(error for error in (port_error, activity_error) if error) or None
        )
    else:
        ports = PORTWATCH.decorate(available_ports, {}, {}, None)

    chokepoint_error = chokepoint_catalog_error or chokepoint_latest_error
    chokepoints: list[dict] = []
    if selected_chokepoint_day is not None and available_chokepoints:
        chokepoints, activity_error = load_chokepoints(
            available_chokepoints,
            selected_chokepoint_day,
            refresh_revision,
            revisions["chokepoints"],
        )
        chokepoint_error = (
            "；".join(error for error in (chokepoint_error, activity_error) if error)
            or None
        )
    else:
        chokepoints = PORTWATCH.decorate_chokepoints(available_chokepoints, {})

    tracks = {}
    if query.include_tracks:
        tracks = vessel_tracks(
            tuple(
                (str(v["mmsi"]), v.get("observed_at"), v["lat"], v["lon"])
                for v in live_positions
            ),
            display_revisions["ais"],
            str(data_store.database_path()),
        )
    import htfa.monitoring.energy_supply.processing.production_units as production

    chosen_assets, asset_rows, _, _ = production.statistical_view(
        assets, query.countries, query.products
    )
    map_assets = production.map_units(assets, chosen_assets, asset_rows)
    view_state = DashboardViewState(
        live_positions=live_positions,
        ais_status=ais_status,
        open_state=open_state,
        archive_error=open_state.get("archive_error"),
        port_error=port_error,
        chokepoint_error=chokepoint_error,
        map_assets=map_assets,
        map_ports=ports,
        map_chokepoints=chokepoints,
        selected_day=selected_day,
        selected_chokepoint_day=selected_chokepoint_day,
        snapshot_day=query.selected_day,
        selected_sea_day=selected_sea_day,
        vessel_tracks=tracks,
        assets=assets,
    )

    return view_state
