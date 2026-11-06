"""Geographic definitions for PortWatch and the broader AIS corridor."""

MONITORED_REGIONS = {
    "霍尔木兹海峡": (25.7, 27.4, 55.9, 57.5),
    "阿曼湾": (22.0, 26.6, 56.0, 61.8),
    "波斯湾": (23.5, 30.9, 47.0, 56.8),
    "苏伊士运河": (29.4, 31.6, 31.7, 33.5),
    "曼德海峡": (11.0, 15.4, 42.0, 45.7),
}

# AIS also follows the Red Sea corridor between Suez and Bab el-Mandeb.
# Keep these after the five named waters so their positions retain those names.
AIS_REGIONS = {
    **MONITORED_REGIONS,
    "红海北段": (21.0, 30.0, 32.0, 40.0),
    "红海南段": (12.0, 21.0, 36.0, 44.0),
    "红海北部两湾": (28.1396, 30.5, 32.0, 35.8),
    "亚丁湾": (10.3781, 15.2197, 42.5134, 51.2867),
}

# Include positions on BOTH sides of the published four-sea boundaries. These
# collection boxes are query limits, never the event-counting boundaries.
AIS_COLLECTION_REGIONS = {
    "波斯湾": (23.6590, 31.4859, 47.4024, 57.6400),
    "阿曼湾": (22.1749, 26.2435, 55.9680, 62.0825),
    "亚丁湾": (10.0780, 15.5197, 42.2134, 51.5867),
    "红海北段": (20.3, 28.4396, 33.3393, 43.8056),
    "红海南段": (12.1562, 20.3, 33.3393, 43.8056),
    # Gulf of Suez / Gulf of Aqaba extend north of the IHO Red Sea polygon.
    "红海北部两湾": (28.1396, 30.5, 32.0, 35.8),
    "苏伊士运河": MONITORED_REGIONS["苏伊士运河"],
    "曼德海峡": MONITORED_REGIONS["曼德海峡"],
}


def region_for(lat: float, lon: float, regions: dict = MONITORED_REGIONS) -> str | None:
    """Use definition order to assign a point in overlapping region boxes once."""
    return next(
        (
            name
            for name, (south, north, west, east) in regions.items()
            if south <= lat <= north and west <= lon <= east
        ),
        None,
    )
