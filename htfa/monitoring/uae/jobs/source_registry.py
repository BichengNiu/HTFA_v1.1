"""The UAE sources supported by both update and workbook merge commands."""

SOURCES = (
    "baker_hughes",
    "oil",
    "cbuae",
    "ded",
    "dld",
    "dot_t100",
    "dubai_customs_air",
    "emsteel",
    "employment",
    "eia_liquids",
    "fcsc",
    "fcsc_gdp",
    "fcsc_annual",
    "wdi_gcc",
    "foreign_labour",
    "pmi",
    "portwatch",
    "public_market",
    "wam",
)

# Discontinued sources cannot be selected by update or workbook merge.
RETIRED_SOURCES = {
    "cloudflare_radar": ("cloudflare_radar_daily", "日度_CloudflareRadar"),
    "comtrade": ("comtrade_monthly", "月度_UNComtrade"),
    "comtrade_vehicles": ("comtrade_vehicles_monthly", "月度_汽车进口"),
    "rta": ("rta_transport_monthly", "月度_RTA交通"),
    "salik": ("salik_active_vehicles_quarterly", "季度_Salik"),
    "gfs": ("gfs_quarterly", "季度_GFS"),
    "energy_supply": ("energy_supply.report_indicators", "月度_能源港口"),
    "uaewps": ("uaewps_monthly", "季度_UAEWPS"),
    "emirates_post": ("detail.emirates_post_monthly", "月度_邮政"),
    "eurostat_air": ("detail.eurostat_air_monthly", "月度_Eurostat航空"),
    "steel": ("mesteel_monthly", "月度_MEsteel"),
    "tdra": ("tdra_telecom_monthly", "月度_TDRA"),
    "scad": ("scad_monthly", "月度_SCAD"),
}


def resolve_source_names(specifier: str) -> list[str]:
    if specifier.strip().casefold() == "all":
        return list(SOURCES)
    names = [name.strip() for name in specifier.split(",") if name.strip()]
    if not names:
        raise ValueError("At least one UAE source is required")
    unknown = [name for name in names if name not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")
    return names
