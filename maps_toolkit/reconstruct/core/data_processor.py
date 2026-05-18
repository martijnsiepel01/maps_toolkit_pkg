# src/core/data_processor.py
"""
A fully dynamic version of DataProcessor.

*   **Mandatory** columns for each source are enforced at load-time
    (see `config_loader.get_required_mapping()`).
*   Every other column is considered **optional** and will be passed
    straight through to the JSON output - no code changes needed when
    you add or remove optional columns in *config.yaml*.

The only fields that are *never* copied to the JSON are the ones used
purely for internal housekeeping (listed in `ALWAYS_IGNORE`).
"""

from __future__ import annotations

import json
import datetime as _dt
from pathlib import Path
from typing import Dict, Any, Optional, List, Set

import pandas as pd
import numpy as np
from pandas import Timestamp
from datetime import timedelta
import os

from tqdm import tqdm
import statistics

from .config_loader import (
    get_column_mapping,
    get_required_mapping,
    find_source_by_role,
    ConfigurationError,
)
from .fast_index import TimeKeyIndex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_dt(x) -> bool:
    return isinstance(x, (Timestamp, _dt.datetime))


def _fmt_dt(x) -> Optional[str]:
    """Format Timestamp → str, keep None/NaT as None, leave others intact."""
    if pd.isna(x):
        return None
    if _is_dt(x):
        return x.strftime("%Y-%m-%d %H:%M:%S")
    return x


def _row_to_dict(row: pd.Series, ignore: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    Convert a Series to a JSON-ready dict, keeping *all* non-NA columns
    except those in *ignore*.
    """
    ignore = ignore or set()
    out: Dict[str, Any] = {}
    for col, val in row.items():
        if col in ignore or pd.isna(val):
            continue

        # Convert NumPy scalar to native Python type
        if isinstance(val, (np.generic,)):
            val = val.item()

        out[col] = _fmt_dt(val)
    return out


# House-keeping columns that should never leak to JSON
ALWAYS_IGNORE: Set[str] = {
    "group",  # internal treatment group id
}

# ------------------------------------------------------------
# constants - tweak once, use everywhere
# ------------------------------------------------------------
SIZE_THRESHOLD = 300 * 1024 * 1024  # 300 MB
DEFAULT_CHUNKSIZE = 2_000_000  # rows per chunk


class DataProcessor:
    # ----------------------------------------------------------
    def __init__(self, config: Dict[str, Any], project_name: str = ""):
        self.config = config
        self.project_name = project_name
        self.data_sources: Dict[str, pd.DataFrame] = {}
        self.data_sources_idx: Dict[str, pd.core.groupby.DataFrameGroupBy] = {}
        self.load_data_sources()

        # Build fast lookup for the admissions source (found by role, not name)
        adm_src = find_source_by_role(self.config, "admissions")
        adm_df = self.data_sources.get(adm_src) if adm_src else None
        if adm_df is not None and not adm_df.empty:
            self._adm_by_contact = (
                adm_df
                .sort_values("admission_start")
                .drop_duplicates("patient_contact_id")
                .set_index("patient_contact_id", drop=False)
            )
        else:
            self._adm_by_contact = None


    # -----------------------------------------------------------------
    # helper: build read‑csv kwargs that match the chosen engine
    # -----------------------------------------------------------------
    @staticmethod
    def _build_read_kw(
        delimiter: str, raw_cols: list, date_cols: list, use_arrow: bool
    ) -> dict:
        if use_arrow:  # fast path, whole file
            return dict(
                delimiter=delimiter,
                usecols=raw_cols,
                parse_dates=date_cols,
                engine="pyarrow",
                dtype_backend="pyarrow",
            )
        # C engine → supports chunksize
        return dict(
            delimiter=delimiter,
            usecols=raw_cols,
            parse_dates=date_cols,
            engine="c",
            low_memory=False,
        )

    # -----------------------------------------------------------------
    # helper: stream a large CSV in chunks and concat in memory
    # -----------------------------------------------------------------
    @staticmethod
    def _read_large_csv(
        path: str,
        read_kw: dict,
        filter_cols: Optional[List[str]] = None,
        keep_keys: Optional[pd.DataFrame] = None,
        chunksize: int = DEFAULT_CHUNKSIZE,
    ) -> pd.DataFrame:
        """Stream a large CSV in chunks and optionally filter by keys."""
        chunks = []
        for chunk in pd.read_csv(path, chunksize=chunksize, **read_kw):
            if filter_cols and keep_keys is not None:
                # Make sure both sides of the join have identical, numeric dtypes
                for col in filter_cols:
                    chunk[col] = pd.to_numeric(chunk[col], errors="coerce").astype("Int64")
                    keep_keys[col] = keep_keys[col].astype("Int64")        # once is enough
                chunk = chunk.merge(keep_keys, on=filter_cols, how="inner")
            chunks.append(chunk)
        return pd.concat(chunks, ignore_index=True)

    # -----------------------------------------------------------------
    # automatic, size‑aware loader
    # -----------------------------------------------------------------
    def load_data_sources(self) -> None:
        """
        Build `self.data_sources` (and `self.data_sources_idx` when
        `index: [...]` is present) entirely from the YAML config.
        Files > 300 MB are streamed in chunks; smaller ones use the
        Arrow engine in a single read.
        """
        self.data_sources = {}
        self.data_sources_idx = {}
        pres_keys: Optional[pd.DataFrame] = None

        for src, scfg in self.config["data_sources"].items():
            if not scfg.get("enabled", False):
                continue

            file_path = scfg["file_path"]
            print(f"--- Loading source: {src} ---")
            print(f"[DEBUG] File path: {file_path}")
            _, ext = os.path.splitext(file_path)
            delimiter = "\t" if ext.lower() in {".tsv", ".txt"} else ","

            # -------- column mapping & date detection --------------------
            mapping = get_column_mapping(self.config, src)
            raw_cols = list(mapping.values())
            date_cols = [
                c for c in raw_cols if c.lower().endswith(("_time", "_datetime"))
            ]

            # -------- choose engine & read strategy ----------------------
            file_is_big = os.path.getsize(file_path) > SIZE_THRESHOLD
            print(f"[DEBUG] File size: {os.path.getsize(file_path)} bytes; File name: {file_path}")
            use_arrow = not file_is_big
            read_kw = self._build_read_kw(delimiter, raw_cols, date_cols, use_arrow)

            if file_is_big:
                filter_cols = []
                if pres_keys is not None:
                    if "patient_id" in scfg["columns"]["required"]:
                        filter_cols.append(scfg["columns"]["required"]["patient_id"])
                    if "patient_contact_id" in scfg["columns"]["required"]:
                        filter_cols.append(
                            scfg["columns"]["required"]["patient_contact_id"]
                        )
                keep = None
                if pres_keys is not None and filter_cols:
                    rename_map = {"patient_id": filter_cols[0]}
                    if len(filter_cols) > 1:
                        rename_map["patient_contact_id"] = filter_cols[1]
                    keep = pres_keys[list(rename_map.keys())].rename(columns=rename_map)
                df = self._read_large_csv(
                    file_path,
                    read_kw,
                    filter_cols=filter_cols if filter_cols else None,
                    keep_keys=keep,
                )
            else:
                df = pd.read_csv(file_path, **read_kw)

            print(f"[DEBUG] Loaded {len(df)} rows from {src}")

            # -------- internal column names ------------------------------
            df.rename(columns={v: k for k, v in mapping.items()}, inplace=True)

            if src == "prescriptions":
                pres_keys = df[["patient_id", "patient_contact_id"]].drop_duplicates()

            # -------- ensure ALL *_datetime / *_time cols are proper dt ---
            for col in df.columns:
                if col.lower().endswith(("_datetime", "_time")):
                    if not pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                    if getattr(df[col].dt, "tz", None) is not None:
                        df[col] = df[col].dt.tz_localize(None)

            # -------- harmonise ID columns (guards against Arrow merge bug)
            if 'patient_contact_id' in df.columns:
                df['patient_contact_id'] = pd.to_numeric(df['patient_contact_id'], errors='coerce').astype('Int64')

            if 'patient_id' in df.columns:
                _numeric = pd.to_numeric(df['patient_id'], errors='coerce')
                if _numeric.notna().all():
                    df['patient_id'] = _numeric.astype('Int64').astype(str)
                else:
                    df['patient_id'] = df['patient_id'].astype(str)

            # -------- validate required columns --------------------------
            missing = [
                c for c in get_required_mapping(self.config, src) if c not in df.columns
            ]
            if missing:
                raise ConfigurationError(f"{src}: missing required {missing}")

            # -------- optional index for O(1) look‑ups -------------------
            default_idx = [
                c for c in ("patient_id", "patient_contact_id") if c in df.columns
            ]
            idx_cols = scfg.get("index", default_idx)
            if idx_cols and src != "measurements":
                df.set_index(idx_cols, inplace=True, drop=False)
                self.data_sources_idx[src] = df.groupby(level=idx_cols)

            self.data_sources[src] = df

        # Build fast time indices for sources that use time-window matching
        self._prepare_fast_indices()

    def _prepare_fast_indices(self) -> None:
        """Prepare per-source TimeKeyIndex for fast time-window slicing."""
        self._time_indices: Dict[str, TimeKeyIndex] = {}
        for source, scfg in self.config["data_sources"].items():
            if not scfg.get("enabled", False):
                continue
            if scfg.get("role") != "treatment_level":
                continue
            mcfg = scfg.get("match", {})
            tw = mcfg.get("time_window")
            if not tw:
                continue

            df = self.data_sources.get(source)
            if df is None or df.empty:
                print(f"[FastIndex] Skipping {source}: no data frame or empty")
                continue

            key_cols = mcfg.get("on") or []
            key_cols = [k for k in key_cols if k in df.columns]
            if not key_cols:
                print(f"[FastIndex] Skipping {source}: no key columns found in df")
                continue

            time_col = tw.get("column")
            if not time_col or time_col not in df.columns:
                print(f"[FastIndex] Skipping {source}: time column '{time_col}' missing")
                continue

            for catcol in (
                c
                for c in [
                    "material_category",
                    "measure_type",
                    "medication_name",
                    "specialty",
                ]
                if c in df.columns
            ):
                if not pd.api.types.is_categorical_dtype(df[catcol]):
                    df[catcol] = df[catcol].astype("category")

            try:
                self._time_indices[source] = TimeKeyIndex(
                    df=df, key_cols=key_cols, time_col=time_col
                )
                print(
                    f"[FastIndex] Built for {source}: "
                    f"{len(self._time_indices[source].keys())} key combinations"
                )
            except Exception as e:
                print(f"[FastIndex] Skipping {source}: {e}")

        print("[FastIndex] Final sources with indices:", list(self._time_indices.keys()))

    def process_data(self) -> Dict[str, Any]:
        prescriptions_df = self.data_sources["prescriptions"].reset_index(drop=True)
        result: Dict[str, Any] = {}
        patient_level_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for src, scfg in self.config["data_sources"].items():
            if not scfg.get("enabled", False):
                continue
            if src == "prescriptions":
                continue
            if scfg.get("match"):
                continue
            src_df = self.data_sources.get(src)
            if src_df is None or src_df.empty:
                continue
            nest_as = scfg.get("nest_as")
            pid_map: Dict[str, Dict[str, Any]] = {}
            for _, row in src_df.iterrows():
                pid = str(row["patient_id"])
                fields = _row_to_dict(row, ignore={"patient_id"})
                if nest_as:
                    pid_map[pid] = {nest_as: fields}
                else:
                    pid_map[pid] = fields
            patient_level_maps[src] = pid_map

        for patient_id, pt_df in tqdm(
            prescriptions_df.groupby("patient_id"), desc="Processing patients"
        ):
            admissions: List[Dict[str, Any]] = []
            next_group_id = 0

            for adm_id, adm_df in pt_df.groupby("patient_contact_id"):
                adm_df = self._create_treatment_groups(adm_df)
                adm_df["group"] += next_group_id
                next_group_id   = adm_df["group"].max() + 1
                admissions.append(self._process_admission(adm_id, adm_df))

            patient_block: Dict[str, Any] = {}
            for src_map in patient_level_maps.values():
                patient_block.update(src_map.get(str(patient_id), {}))
            patient_block["admissions"] = admissions
            result[str(patient_id)] = patient_block

        return result

    def _create_treatment_groups(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.sort_values("start_datetime")
        start = df["start_datetime"].fillna(df["stop_datetime"])
        stop = df["stop_datetime"].fillna(df["start_datetime"])
        prev_end = stop.cummax().shift()
        prev_end.iloc[0] = stop.iloc[0]
        gap = start > prev_end + pd.Timedelta(hours=24)
        df["group"] = gap.astype("bool").to_numpy().cumsum().astype(int)
        return df

    def _process_admission(self, adm_id: str, adm_df: pd.DataFrame) -> Dict[str, Any]:
        info = self._get_admission_info(adm_id)
        treatments: List[Dict[str, Any]] = []
        for grp_id, grp_df in adm_df.groupby("group"):
            treatments.append(self._process_treatment(grp_id, grp_df))

        adm_dict = _row_to_dict(pd.Series(info), ignore=set())
        adm_dict.update(
            {
                "patient_contact_id": adm_id,
                "treatments": treatments,
            }
        )

        return adm_dict

    def _get_admission_info(self, adm_id: str) -> Dict[str, Any]:
        if getattr(self, "_adm_by_contact", None) is None:
            return {}
        try:
            row = self._adm_by_contact.loc[adm_id]
        except KeyError:
            return {}
        return row.to_dict()

    def _process_treatment(self, grp_id: int, grp_df: pd.DataFrame) -> Dict[str, Any]:
        grp_df = grp_df.drop_duplicates()
        t_start = grp_df["start_datetime"].min()
        t_end = grp_df["stop_datetime"].max()

        prescriptions = [self._process_prescription(r) for _, r in grp_df.iterrows()]

        dynamic_blocks: Dict[str, Any] = {}
        for source, scfg in self.config["data_sources"].items():
            if not scfg.get("enabled", False):
                continue
            if scfg.get("role") != "treatment_level":
                continue

            matches = self._match_additional_data(
                source=source,
                treatment_df=grp_df,
                treatment_anchor=t_start,
                treatment_end=t_end,
            )
            if matches:
                dynamic_blocks[source] = matches

        return {
            "treatment_id": int(grp_id),
            "treatment_start": _fmt_dt(t_start),
            "treatment_end": _fmt_dt(t_end),
            "prescriptions": prescriptions,
            **dynamic_blocks,
        }

    def _process_prescription(self, row: pd.Series) -> Dict[str, Any]:
        return _row_to_dict(row, ignore=ALWAYS_IGNORE)

    def _match_additional_data(
        self,
        source: str,
        treatment_df: pd.DataFrame,
        treatment_anchor: Timestamp,
        treatment_end: Timestamp,
    ) -> List[Dict[str, Any]]:
        scfg = self.config["data_sources"].get(source, {})
        mcfg = scfg.get("match", {})
        key_cols = mcfg.get("on") or []
        tw = mcfg.get("time_window")

        idx = getattr(self, "_time_indices", {}).get(source)
        if tw and key_cols and idx is None:
            raise ConfigurationError(
                f"{source}: time_window is configured but no fast TimeKeyIndex is available. "
                "Check _prepare_fast_indices or adjust the config."
            )

        if idx is None or not key_cols or not tw:
            if source not in self.data_sources:
                return []
            df = self.data_sources[source].reset_index(drop=True)

            if key_cols:
                if not all(k in treatment_df.columns and k in df.columns for k in key_cols):
                    return []
                key_combos = treatment_df[key_cols].dropna().drop_duplicates()
                df = df.merge(key_combos, on=key_cols, how="inner")
                if df.empty:
                    return []

            if tw and not df.empty:
                tcol = tw.get("column")
                if not tcol or tcol not in df.columns:
                    return []
                if (
                    pd.api.types.is_datetime64_any_dtype(df[tcol])
                    and df[tcol].dt.tz is not None
                ):
                    df[tcol] = df[tcol].dt.tz_localize(None)

                before = int(tw.get("before_hours", 0))
                after_raw = tw.get("after_hours", 0)
                if after_raw == "until_end":
                    t1 = treatment_end
                else:
                    t1 = treatment_anchor + timedelta(hours=int(after_raw))
                t0 = treatment_anchor - timedelta(hours=before)
                df = df[(df[tcol] >= t0) & (df[tcol] <= t1)]

            return [_row_to_dict(r, ignore=set()) for _, r in df.iterrows()]

        # Fast path using index
        tw = mcfg.get("time_window") or {}
        before = int(tw.get("before_hours", 0))
        after_raw = tw.get("after_hours", 0)
        if after_raw == "until_end":
            t1 = treatment_end
        else:
            t1 = treatment_anchor + timedelta(hours=int(after_raw))
        t0 = treatment_anchor - timedelta(hours=before)

        if not all(k in treatment_df.columns for k in key_cols):
            return []

        row0 = treatment_df.iloc[0]
        key_tuple = tuple(row0[k] for k in key_cols)

        matched = idx.slice_window(key_tuple, t0, t1)
        if matched.empty:
            return []

        return [_row_to_dict(r, ignore=set()) for _, r in matched.iterrows()]

    def save_output(self, result: Dict[str, Any]) -> None:
        path = self.config["output"]["file_path"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fmt = str(self.config.get("output", {}).get("format", "json")).lower()

        def sanitize_for_json(obj):
            if isinstance(obj, dict):
                return {k: sanitize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_for_json(v) for v in obj]
            elif isinstance(obj, (np.generic,)):
                return obj.item()
            elif pd.isna(obj):
                return None
            elif isinstance(obj, pd.Timestamp):
                return obj.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(obj, _dt.datetime):
                return obj.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(obj, _dt.date):
                return obj.strftime("%Y-%m-%d")
            return obj

        if fmt == "jsonl":
            with open(path, "w", encoding="utf-8") as fh:
                for pid, block in result.items():
                    fh.write(
                        json.dumps({str(pid): sanitize_for_json(block)}, ensure_ascii=False)
                        + "\n"
                    )
        else:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(sanitize_for_json(result), fh, indent=4, ensure_ascii=False)

    def summarize_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        num_patients = len(result)
        num_treatments = 0
        num_prescriptions = 0

        prescription_durations: List[float] = []
        treatment_durations: List[float] = []
        starts_per_month: Dict[str, int] = {}

        for patient in result.values():
            for adm in patient.get("admissions", []):
                for treatment in adm.get("treatments", []):
                    num_treatments += 1

                    t_start = treatment.get("treatment_start")
                    t_end = treatment.get("treatment_end")
                    if t_start and t_end:
                        ts = pd.to_datetime(t_start)
                        te = pd.to_datetime(t_end)
                        dur = (te - ts).total_seconds() / 3600.0
                        if dur >= 0:
                            treatment_durations.append(dur)
                        ym = f"{ts.year}-{ts.month:02d}"
                        starts_per_month[ym] = starts_per_month.get(ym, 0) + 1

                    for pres in treatment.get("prescriptions", []):
                        num_prescriptions += 1
                        p_start = pres.get("start_datetime")
                        p_end = pres.get("stop_datetime")
                        if p_start:
                            ps = pd.to_datetime(p_start)
                            pe = pd.to_datetime(p_end) if p_end else ps + timedelta(minutes=10)
                            dur = (pe - ps).total_seconds() / 3600.0
                            if dur >= 0:
                                prescription_durations.append(dur)

        avg_prescriptions_per_treatment = (
            num_prescriptions / num_treatments if num_treatments else 0
        )

        median_prescription_len = (
            statistics.median(prescription_durations)
            if prescription_durations
            else 0
        )
        median_treatment_len = (
            statistics.median(treatment_durations)
            if treatment_durations
            else 0
        )

        return {
            "patients": num_patients,
            "treatments": num_treatments,
            "prescriptions": num_prescriptions,
            "average_prescriptions_per_treatment": avg_prescriptions_per_treatment,
            "median_prescription_duration_hours": median_prescription_len,
            "median_treatment_duration_hours": median_treatment_len,
        }
