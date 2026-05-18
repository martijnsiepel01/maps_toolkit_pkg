"""Generic treatment duration analysis plugins."""
import pandas as pd
from maps_toolkit.analyze.utils import parse_datetime, get_nested


def _duration_days(treatment: dict, start_field: str, end_field: str):
    start = parse_datetime(treatment.get(start_field))
    end = parse_datetime(treatment.get(end_field))
    if start is None or end is None:
        return None
    return (end - start).total_seconds() / 86400.0


def by_group(treatments: list, params: dict) -> pd.DataFrame:
    """
    Compute treatment duration aggregated by a group field.

    params:
      group_field: dotted path into treatment dict (e.g. "prescriptions.0.group_admission")
      start_field: field name for treatment start (default: "treatment_start")
      end_field:   field name for treatment end   (default: "treatment_end")
      aggregations: list of ["count", "median", "iqr", "mean"] (default: all three)
    """
    group_field = params["group_field"]
    start_field = params.get("start_field", "treatment_start")
    end_field = params.get("end_field", "treatment_end")
    aggs = set(params.get("aggregations", ["count", "median", "iqr"]))

    rows = []
    for t in treatments:
        d = _duration_days(t, start_field, end_field)
        if d is not None:
            rows.append({"_group": get_nested(t, group_field), "duration_days": float(d)})

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    agg_fns = {}
    if "count" in aggs:
        agg_fns["treatment_count"] = ("duration_days", "count")
    if "median" in aggs:
        agg_fns["median_duration_days"] = ("duration_days", "median")
    if "iqr" in aggs:
        agg_fns["iqr_duration_days"] = (
            "duration_days", lambda x: x.quantile(0.75) - x.quantile(0.25)
        )
    if "mean" in aggs:
        agg_fns["mean_duration_days"] = ("duration_days", "mean")

    result = df.groupby("_group", dropna=False).agg(**agg_fns).reset_index()
    return result.rename(columns={"_group": group_field})


def values_by_group(treatments: list, params: dict) -> pd.DataFrame:
    """
    Return one row per treatment with duration and an optional group field.

    params:
      group_field: dotted path (optional)
      start_field / end_field: as above
      dropna: drop rows with null duration (default True)
    """
    group_field = params.get("group_field")
    start_field = params.get("start_field", "treatment_start")
    end_field = params.get("end_field", "treatment_end")
    dropna = params.get("dropna", True)

    rows = []
    for t in treatments:
        d = _duration_days(t, start_field, end_field)
        row = {"duration_days": d}
        if group_field:
            row[group_field] = get_nested(t, group_field)
        rows.append(row)

    df = pd.DataFrame(rows)
    if dropna:
        df = df.dropna(subset=["duration_days"])
    return df.reset_index(drop=True)
