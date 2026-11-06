"""Keep energy monitoring widget and session keys in their own namespace."""


def energy_key(value: str) -> str:
    """Return the stable HTFA key for an energy monitoring control."""
    if value == "energy_supply" or value.startswith("energy_supply_"):
        return value
    return f"energy_supply_{value}"
