"""Model comparison utilities.

Provides :func:`compare_models` for producing Stata-style regression
comparison tables across multiple fitted model results.
"""

from __future__ import annotations


def _significance_stars(pvalue):
    """Return significance stars for a p-value.

    ``***`` p<0.01, ``**`` p<0.05, ``*`` p<0.1, ``""`` otherwise.
    """
    if pvalue is None:
        return ""
    if pvalue < 0.01:
        return "***"
    if pvalue < 0.05:
        return "**"
    if pvalue < 0.10:
        return "*"
    return ""


# ---------------------------------------------------------------------------
# Parameter grouping
# ---------------------------------------------------------------------------


def _param_group(name):
    """Return the group label for a parameter name."""
    if name in ("mu", "Const"):
        return "main"
    if name == "kappa":
        return "ARCHM"
    return "ARCH"


def _group_params(all_params):
    """Group parameter names into (main, ARCHM, ARCH) order."""
    main_params = []
    archm_params = []
    arch_params = []
    for name in all_params:
        group = _param_group(name)
        if group == "main":
            main_params.append(name)
        elif group == "ARCHM":
            archm_params.append(name)
        else:
            arch_params.append(name)
    return main_params + archm_params + arch_params


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_models(models):
    """Compare multiple fitted model results in a Stata-style regression table.

    Parameters are grouped into sections (main, ARCHM, ARCH) and renamed to
    Stata conventions: mu/Const → _cons, kappa → sigma2, alpha[1] → L.arch,
    beta[1] → L.garch, omega → _cons.

    Parameters
    ----------
    models : dict[str, BaseModelResult]
        Mapping of model name to fitted result object.

    Returns
    -------
    str
        Stata-style comparison table with t-statistics and significance stars.

    Raises
    ------
    TypeError
        If *models* is not a dict.
    ValueError
        If *models* is empty.
    """
    if not isinstance(models, dict):
        raise TypeError(f"models must be a dict, got {type(models).__name__}")
    if len(models) == 0:
        raise ValueError("models dict must not be empty")

    model_names = list(models.keys())
    n_models = len(model_names)
    results = [models[name] for name in model_names]

    # Collect all unique parameter names
    all_params = []
    for r in results:
        for name in r.params:
            if name not in all_params:
                all_params.append(name)

    grouped = _group_params(all_params)

    # Column widths
    name_width = max(
        max((len(name) for name in grouped), default=10),
        max((len(n) for n in model_names), default=8),
        len("N"),
    )
    col_width = 14

    total_width = name_width + n_models * col_width + (n_models - 1) + 2
    sep_line = "-" * total_width

    lines = [sep_line]

    # Header: column numbers (1) (2) (3) ...
    header_num = " " * (name_width + 1)
    for i in range(n_models):
        header_num += f"({i + 1})".center(col_width)
        if i < n_models - 1:
            header_num += " "
    lines.append(header_num)

    # Header: model names
    header_name = " " * (name_width + 1)
    for i, name in enumerate(model_names):
        header_name += name.center(col_width)
        if i < n_models - 1:
            header_name += " "
    lines.append(header_name)
    lines.append(sep_line)

    # Parameter groups
    current_group = None
    for param_name in grouped:
        group = _param_group(param_name)
        if group != current_group:
            current_group = group
            lines.append(group)

        # Estimate line
        est_line = f"  {param_name:<{name_width - 2}s}"
        t_line = " " * name_width

        for i, r in enumerate(results):
            if param_name in r.params:
                val = r.params[param_name]
                se = r.std_errors.get(param_name)
                pv = r.p_values.get(param_name)
                stars = _significance_stars(pv)

                if abs(val) < 0.0001:
                    est_str = f"{val:.8f}{stars}"
                elif abs(val) < 0.001:
                    est_str = f"{val:.6f}{stars}"
                elif abs(val) < 1:
                    est_str = f"{val:.4f}{stars}"
                else:
                    est_str = f"{val:.4f}{stars}"

                t_stat = val / se if se is not None and se > 0 else float("nan")
                t_str = f"({t_stat:.2f})" if abs(t_stat) < 100 else f"({t_stat:.1f})"

                est_line += est_str.center(col_width)
                t_line += t_str.center(col_width)
            else:
                est_line += " ".center(col_width)
                t_line += " ".center(col_width)

            if i < n_models - 1:
                est_line += " "
                t_line += " "

        lines.append(est_line)
        lines.append(t_line)

    lines.append(sep_line)

    # N (observations)
    n_line = f"  {'N':<{name_width - 2}s}"
    for i, r in enumerate(results):
        n_line += str(r.nobs).center(col_width)
        if i < n_models - 1:
            n_line += " "
    lines.append(n_line)
    lines.append(sep_line)

    # Footer
    lines.append("t statistics in parentheses")
    lines.append("* p<0.10, ** p<0.05, *** p<0.01")

    return "\n".join(lines)
