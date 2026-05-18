"""Generic field-selection and aggregation plugins."""
import pandas as pd
from maps_toolkit.analyze.utils import get_nested


def select(treatments: list, params: dict) -> pd.DataFrame:
    """
    Extract named fields from each treatment dict into a flat DataFrame.

    params:
      fields: list of {name: str, path: str} dicts
              name  = output column name
              path  = dotted path into the treatment dict
      dropna: drop rows with any null value (default True)
    """
    fields = params.get("fields", [])
    dropna = params.get("dropna", True)

    rows = []
    for t in treatments:
        row = {f["name"]: get_nested(t, f["path"]) for f in fields}
        rows.append(row)

    df = pd.DataFrame(rows)
    if dropna:
        df = df.dropna()
    return df.reset_index(drop=True)
