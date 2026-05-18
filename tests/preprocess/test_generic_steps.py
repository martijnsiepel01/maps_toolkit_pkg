# tests/preprocess/test_generic_steps.py
import pandas as pd
import pytest
from maps_toolkit.preprocess.generic import (
    rename_columns, drop_columns, select_columns, uppercase_column_names,
    filter_rows_by_value, filter_rows_by_pattern, filter_rows_by_date_range,
    drop_duplicates, parse_datetimes, cast_to_integer, cast_to_string,
    fillna, map_values, join_file, get_builtin,
)

CTX = {}  # empty context sufficient for all built-in steps

def test_rename_columns():
    df = pd.DataFrame({"OLD": [1, 2], "KEEP": [3, 4]})
    result = rename_columns(df, {"OLD": "new"}, CTX)
    assert list(result.columns) == ["new", "KEEP"]

def test_rename_columns_ignores_missing():
    df = pd.DataFrame({"A": [1]})
    result = rename_columns(df, {"MISSING": "x"}, CTX)
    assert list(result.columns) == ["A"]

def test_drop_columns():
    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    result = drop_columns(df, {"columns": ["A", "B"]}, CTX)
    assert list(result.columns) == ["C"]

def test_drop_columns_ignores_missing():
    df = pd.DataFrame({"A": [1]})
    result = drop_columns(df, {"columns": ["A", "GONE"]}, CTX)
    assert result.empty

def test_select_columns():
    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    result = select_columns(df, {"columns": ["A", "C"]}, CTX)
    assert list(result.columns) == ["A", "C"]

def test_uppercase_column_names():
    df = pd.DataFrame({"abc": [1], "Def": [2]})
    result = uppercase_column_names(df, {}, CTX)
    assert list(result.columns) == ["ABC", "DEF"]

def test_filter_rows_by_value():
    df = pd.DataFrame({"code": ["J01", "J02", "A01"]})
    result = filter_rows_by_value(df, {"column": "code", "values": ["J01", "J02"]}, CTX)
    assert len(result) == 2
    assert "A01" not in result["code"].values

def test_filter_rows_by_pattern_startswith():
    df = pd.DataFrame({"code": ["J01CA", "J02", "A01"]})
    result = filter_rows_by_pattern(df, {"column": "code", "startswith": "J01"}, CTX)
    assert len(result) == 1
    assert result["code"].iloc[0] == "J01CA"

def test_filter_rows_by_pattern_regex():
    df = pd.DataFrame({"val": ["abc", "def", "abz"]})
    result = filter_rows_by_pattern(df, {"column": "val", "pattern": "^ab"}, CTX)
    assert len(result) == 2

def test_filter_rows_by_date_range():
    df = pd.DataFrame({"dt": pd.to_datetime(["2020-01-01", "2021-06-01", "2022-01-01"])})
    result = filter_rows_by_date_range(df, {"column": "dt", "start": "2020-06-01", "end": "2021-12-31"}, CTX)
    assert len(result) == 1

def test_drop_duplicates():
    df = pd.DataFrame({"A": [1, 1, 2], "B": ["x", "x", "y"]})
    result = drop_duplicates(df, {"subset": ["A"]}, CTX)
    assert len(result) == 2

def test_parse_datetimes():
    df = pd.DataFrame({"dt_str": ["2023-01-01 08:00:00", "invalid", None]})
    result = parse_datetimes(df, {"columns": ["dt_str"]}, CTX)
    assert pd.api.types.is_datetime64_any_dtype(result["dt_str"])

def test_cast_to_integer():
    df = pd.DataFrame({"id": ["1", "2.0", "bad", None]})
    result = cast_to_integer(df, {"columns": ["id"]}, CTX)
    assert pd.api.types.is_integer_dtype(result["id"])
    assert result["id"].iloc[0] == 1

def test_cast_to_string():
    df = pd.DataFrame({"num": [1, 2, 3]})
    result = cast_to_string(df, {"columns": ["num"]}, CTX)
    assert pd.api.types.is_string_dtype(result["num"])

def test_fillna():
    df = pd.DataFrame({"val": [1.0, None, 3.0]})
    result = fillna(df, {"column": "val", "value": 0}, CTX)
    assert result["val"].iloc[1] == 0

def test_map_values_inline():
    df = pd.DataFrame({"code": ["a", "b", "c"]})
    result = map_values(df, {"column": "code", "mapping": {"a": "alpha", "b": "beta"}}, CTX)
    assert result["code"].iloc[0] == "alpha"
    assert result["code"].iloc[2] == "c"  # unmapped values kept

def test_join_file(tmp_path):
    main = pd.DataFrame({"id": [1, 2, 3], "val": ["x", "y", "z"]})
    other = pd.DataFrame({"id": [1, 2], "extra": ["A", "B"]})
    other_path = tmp_path / "other.csv"
    other.to_csv(other_path, index=False)
    result = join_file(main, {"path": str(other_path), "on": "id", "columns": ["extra"]}, CTX)
    assert "extra" in result.columns
    assert result[result["id"] == 3]["extra"].isna().all()

def test_get_builtin_returns_none_for_unknown():
    assert get_builtin("does_not_exist") is None

def test_get_builtin_returns_function_for_known():
    fn = get_builtin("rename_columns")
    assert callable(fn)


def test_engine_resolves_dict_step(tmp_path):
    """Engine must execute a dict step (built-in) without error."""
    import yaml
    from maps_toolkit.preprocess.engine import run_pipeline

    raw = pd.DataFrame({"old_col": ["a", "b"]})
    raw_path = tmp_path / "input.csv"
    raw.to_csv(raw_path, index=False)
    out_path = tmp_path / "output.csv"

    cfg = {
        "sources": {  # no module needed for built-in steps only
            "test": {
                "input": {"format": "csv", "path": str(raw_path)},
                "steps": [{"rename_columns": {"old_col": "new_col"}}],
                "output": {"path": str(out_path), "format": "csv"},
            }
        },
    }
    cfg_dir = tmp_path / "configs" / "test"
    cfg_dir.mkdir(parents=True)
    cfg_path = cfg_dir / "preprocess.yaml"
    cfg_path.write_text(yaml.dump(cfg), encoding="utf-8")

    run_pipeline(str(cfg_path))
    result = pd.read_csv(out_path)
    assert "new_col" in result.columns
    assert "old_col" not in result.columns
