"""
maps-toolkit preprocess engine.

Reads a YAML config that specifies:
  - an optional Python module (by file path or import path) containing step functions
  - one or more sources with input/output paths and an ordered list of steps

Each step is a callable with signature (df, context) -> df.

Supported input formats:
  - csv / tsv: read from a delimited file
  - parquet: read from a parquet file
  - none: start with an empty DataFrame (source builds its own data)
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import time
from pathlib import Path
from typing import Any, Dict, Callable

import pandas as pd
import yaml

from maps_toolkit.preprocess import generic as _generic


class ConfigError(Exception):
    pass


def _guess_format(path: str, cfg: Dict[str, Any]) -> str:
    fmt = str(cfg.get("format") or "").lower()
    if fmt:
        return fmt
    ext = Path(path).suffix.lower()
    if ext in {".tsv", ".txt"}:
        return "tsv"
    if ext == ".parquet":
        return "parquet"
    return "csv"


def _read_input(cfg: Dict[str, Any], context: Dict[str, Any]) -> pd.DataFrame:
    inp = cfg.get("input", {})
    fmt_raw = str(inp.get("format") or "").lower()

    if fmt_raw == "none":
        return pd.DataFrame()

    path = inp.get("path")
    if not path:
        raise ConfigError("input.path is required (unless input.format is 'none')")

    fmt = _guess_format(path, inp)
    delimiter = inp.get("delimiter")
    if delimiter is None and fmt == "tsv":
        delimiter = "\t"

    if fmt in {"csv", "tsv"}:
        read_kwargs: Dict[str, Any] = {"delimiter": delimiter or ","}
        if inp.get("engine"):
            read_kwargs["engine"] = inp.get("engine")
        return pd.read_csv(path, **read_kwargs)
    if fmt == "parquet":
        return pd.read_parquet(path)

    raise ConfigError(f"Unsupported input format: {fmt}")


def _write_output(df: pd.DataFrame, cfg: Dict[str, Any]) -> None:
    out = cfg.get("output", {})
    path = out.get("path")
    if not path:
        raise ConfigError("output.path is required")
    fmt = _guess_format(path, out)
    delimiter = out.get("delimiter")
    if delimiter is None and fmt == "tsv":
        delimiter = "\t"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if fmt in {"csv", "tsv"}:
        df.to_csv(path, index=False, sep=delimiter or ",")
    elif fmt == "parquet":
        df.to_parquet(path, index=False)
    else:
        raise ConfigError(f"Unsupported output format: {fmt}")


def _load_module(module_path: str):
    """Load a module by file path (*.py) or by importable module name."""
    try:
        if module_path.endswith(".py"):
            spec = importlib.util.spec_from_file_location("_custom_steps", module_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        return importlib.import_module(module_path)
    except Exception as exc:
        raise ConfigError(f"Could not load module '{module_path}': {exc}") from exc


def _load_step(mod, name: str) -> Callable:
    try:
        fn = getattr(mod, name)
    except AttributeError as exc:
        raise ConfigError(f"Step '{name}' not found in module '{mod.__name__}'") from exc
    if not callable(fn):
        raise ConfigError(f"Step '{name}' in module '{mod.__name__}' is not callable")
    return fn


def _validate_steps(steps: list, mod) -> None:
    errors = []
    for step in steps:
        if isinstance(step, dict):
            step_name = next(iter(step))
            if _generic.get_builtin(step_name) is None:
                errors.append(f"Unknown built-in step '{step_name}'")
        elif isinstance(step, str):
            if mod is None or not hasattr(mod, step):
                mod_name = getattr(mod, "__name__", "<none>") if mod else "<no module>"
                errors.append(f"Step '{step}' not found in module '{mod_name}'")
    if errors:
        raise ConfigError("Config errors:\n" + "\n".join(f"  - {e}" for e in errors))


def run_pipeline(config_path: str) -> None:
    t_start = time.time()
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    module_path = cfg.get("module")
    mod = _load_module(module_path) if module_path else None

    sources = cfg.get("sources") or {}
    row_limit = cfg.get("row_limit")
    if row_limit is not None:
        row_limit = int(row_limit)
    if not sources:
        raise ConfigError("Config must contain at least one source under 'sources'")

    for src_name, src_cfg in sources.items():
        print(f"\n=== Processing source: {src_name} ===")
        t0 = time.time()

        context: Dict[str, Any] = {
            "source": src_name,
            "config": src_cfg,
            "db_conn": None,
            "row_limit": row_limit,
        }

        df = _read_input(src_cfg, context)
        src_path = (src_cfg.get("input") or {}).get("path") or "<none>"
        print(f"Loaded {len(df):,} rows from {src_path}")

        raw_out = src_cfg.get("raw_output")
        if raw_out and not df.empty:
            raw_path = raw_out.get("path")
            if raw_path:
                raw_fmt = _guess_format(raw_path, raw_out)
                raw_delim = raw_out.get("delimiter")
                if raw_delim is None and raw_fmt == "tsv":
                    raw_delim = "\t"
                Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
                if raw_fmt in {"csv", "tsv"}:
                    df.to_csv(raw_path, index=False, sep=raw_delim or ",")
                elif raw_fmt == "parquet":
                    df.to_parquet(raw_path, index=False)
                print(f"Saved raw input ({len(df):,} rows) to {raw_path}")

        _validate_steps(src_cfg.get("steps", []), mod)

        for step in src_cfg.get("steps", []):
            step_start = time.time()
            before_rows = len(df)
            if isinstance(step, dict):
                step_name, params = next(iter(step.items()))
                fn = _generic.get_builtin(step_name)
                df = fn(df, params or {}, context)
            else:
                step_name = step
                fn = _load_step(mod, step)
                df = fn(df, context)
            after_rows = len(df)
            elapsed = time.time() - step_start
            print(
                f"  - {step_name}: {before_rows:,} -> {after_rows:,} rows "
                f"({elapsed:.2f}s)"
            )

        _write_output(df, src_cfg)
        print(f"Saved output to {src_cfg['output']['path']} in {time.time() - t0:.2f}s")

    print(f"\nAll sources completed in {time.time() - t_start:.2f}s")


def main(argv: list | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="maps-toolkit preprocess engine."
    )
    parser.add_argument("-c", "--config", required=True, help="Path to YAML config.")
    args = parser.parse_args(argv)

    config_path = args.config
    if not os.path.exists(config_path):
        raise SystemExit(f"Config file not found: {config_path}")

    run_pipeline(config_path)


if __name__ == "__main__":
    main()
