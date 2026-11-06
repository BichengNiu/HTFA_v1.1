"""The UAE sources supported by both update and workbook merge commands."""

SOURCES = (
    "baker_hughes",
    "oil",
    "cbuae",
    "cloudflare_radar",
    "comtrade",
    "comtrade_vehicles",
    "ded",
    "dld",
    "dot_t100",
    "dubai_customs_air",
    "emsteel",
    "energy_supply",
    "employment",
    "eia_liquids",
    "fcsc",
    "fcsc_gdp",
    "fcsc_annual",
    "wdi_gcc",
    "foreign_labour",
    "gfs",
    "pmi",
    "portwatch",
    "public_market",
    "rta",
    "salik",
    "wam",
)

# Discontinued sources cannot be selected by update or workbook merge.
RETIRED_SOURCES = {
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
