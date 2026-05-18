"""
Built-in parametrized preprocessing steps.

Each function has signature (df, params, context) -> df.
Use get_builtin(name) to retrieve a step by name.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

_REGISTRY: dict[str, Any] = {}


def _register(fn):
    _REGISTRY[fn.__name__] = fn
    return fn


def get_builtin(name: str):
    """Return built-in step function by name, or None if not registered."""
    return _REGISTRY.get(name)


@_register
def rename_columns(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    return df.rename(columns={k: v for k, v in params.items() if k in df.columns})


@_register
def drop_columns(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    return df.drop(columns=params.get("columns", []), errors="ignore")


@_register
def select_columns(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    cols = [c for c in params.get("columns", []) if c in df.columns]
    return df[cols]


@_register
def uppercase_column_names(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]
    return df


@_register
def filter_rows_by_value(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    col = params["column"]
    return df[df[col].isin(params["values"])]


@_register
def filter_rows_by_pattern(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    col = params["column"]
    series = df[col].astype(str)
    if "startswith" in params:
        return df[series.str.startswith(params["startswith"], na=False)]
    return df[series.str.contains(params["pattern"], na=False, regex=True)]


@_register
def filter_rows_by_date_range(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    col = params["column"]
    if "start" in params:
        df = df[df[col] >= pd.Timestamp(params["start"])]
    if "end" in params:
        df = df[df[col] <= pd.Timestamp(params["end"])]
    return df


@_register
def drop_duplicates(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    return df.drop_duplicates(
        subset=params.get("subset"), keep=params.get("keep", "first")
    )


@_register
def parse_datetimes(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    for col in params.get("columns", []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


@_register
def cast_to_integer(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    for col in params.get("columns", []):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


@_register
def cast_to_string(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    for col in params.get("columns", []):
        if col in df.columns:
            df[col] = df[col].astype(str)
    return df


@_register
def fillna(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    col = params["column"]
    if col in df.columns:
        df[col] = df[col].fillna(params["value"])
    return df


@_register
def map_values(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    col = params["column"]
    if "mapping_file" in params:
        with open(params["mapping_file"], encoding="utf-8") as fh:
            mapping = yaml.safe_load(fh)
    else:
        mapping = params.get("mapping", {})
    if col in df.columns:
        df[col] = df[col].map(mapping).fillna(df[col])
    return df


@_register
def join_file(df: pd.DataFrame, params: dict, context: dict) -> pd.DataFrame:
    path = params["path"]
    on = params["on"]
    delimiter = params.get("delimiter", ",")
    other = pd.read_csv(path, sep=delimiter, low_memory=False)
    keep_cols = params.get("columns", [c for c in other.columns if c != on])
    cols_to_read = list({on} | set(keep_cols))
    other = other[[c for c in cols_to_read if c in other.columns]]
    return df.merge(other, on=on, how="left")
