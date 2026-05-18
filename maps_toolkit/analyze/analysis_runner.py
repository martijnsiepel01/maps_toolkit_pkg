"""
maps-toolkit analyze runner.

Config format:
  data_path: path to reconstruct JSON
  output_dir: directory for output CSVs
  module: (optional) path to a .py file or dotted module path with custom plugins
  analyses:
    - plugin: "duration.by_group"          # <module>.<function>
      output: "my_output.csv"
      params:
        group_field: "prescriptions.0.group_admission"
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import pkgutil
from pathlib import Path

import pandas as pd
import yaml

import maps_toolkit.analyze.plugins as _builtin_plugins
from maps_toolkit.analyze.utils import load_treatments


class ConfigError(Exception):
    pass


def _discover_builtin_plugins() -> dict:
    """Walk maps_toolkit/analyze/plugins/ and register every public function."""
    plugin_map = {}
    for finder, name, ispkg in pkgutil.walk_packages(
        _builtin_plugins.__path__, _builtin_plugins.__name__ + "."
    ):
        module = importlib.import_module(name)
        short = name.split(".")[-1]
        for fn_name, fn_obj in module.__dict__.items():
            if callable(fn_obj) and fn_obj.__module__ == module.__name__ and not fn_name.startswith("_"):
                plugin_map[f"{short}.{fn_name}"] = fn_obj
    return plugin_map


def _load_custom_plugins(module_path: str) -> dict:
    """Import a user-supplied module (file path or dotted name) and register its public functions."""
    plugin_map = {}
    try:
        if module_path.endswith(".py"):
            spec = importlib.util.spec_from_file_location("_custom_plugins", module_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            short = Path(module_path).stem
        else:
            mod = importlib.import_module(module_path)
            short = module_path.split(".")[-1]
    except Exception as exc:
        raise ConfigError(f"Cannot load custom plugin module '{module_path}': {exc}") from exc

    for fn_name, fn_obj in mod.__dict__.items():
        if callable(fn_obj) and not fn_name.startswith("_"):
            plugin_map[f"{short}.{fn_name}"] = fn_obj
    return plugin_map


def run_analysis(config_path: str) -> None:
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    plugin_map = _discover_builtin_plugins()
    if "module" in cfg:
        plugin_map.update(_load_custom_plugins(cfg["module"]))

    analyses = cfg.get("analyses", [])

    errors = []
    for entry in analyses:
        key = entry.get("plugin", "")
        if key not in plugin_map:
            errors.append(f"Plugin not found: '{key}'")
        if not entry.get("name") and not entry.get("output"):
            errors.append(f"Missing 'name' (or 'output') for plugin '{key}'")
    if errors:
        raise ConfigError("Config errors:\n" + "\n".join(f"  - {e}" for e in errors))

    treatments = load_treatments(cfg["data_path"])

    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    for entry in analyses:
        plugin_key = entry["plugin"]
        params = entry.get("params", {}) or {}
        output_filename = entry.get("output") or (entry["name"] + ".csv")
        output_path = output_dir / output_filename

        print(f"\n--- Running: {plugin_key} -> {output_filename} ---")
        fn = plugin_map[plugin_key]
        result = fn(treatments, params)

        if not isinstance(result, pd.DataFrame):
            raise ConfigError(
                f"Plugin '{plugin_key}' must return a pd.DataFrame, got {type(result)}"
            )

        result.to_csv(output_path, index=False, encoding="utf-8")
        print(f"  Wrote {len(result)} rows to {output_path}")

    print("\n--- Analysis complete ---")


def main(argv=None):
    parser = argparse.ArgumentParser(description="maps-toolkit analyze runner.")
    parser.add_argument("-c", "--config", required=True, help="Path to YAML config.")
    args = parser.parse_args(argv)
    run_analysis(args.config)


if __name__ == "__main__":
    main()
