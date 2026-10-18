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
    "emirates_post",
    "employment",
    "eurostat_air",
    "eia_liquids",
    "fcsc",
    "fcsc_gdp",
    "foreign_labour",
    "gfs",
    "pmi",
    "portwatch",
    "public_market",
    "rta",
    "salik",
    "scad",
    "steel",
    "tdra",
    "uaewps",
    "wam",
)


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
