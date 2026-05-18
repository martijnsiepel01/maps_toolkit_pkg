from __future__ import annotations

from typing import Dict, Tuple, List
import numpy as np
import pandas as pd


class TimeKeyIndex:
    """
    Holds per-key (e.g., patient_id or (patient_id, patient_contact_id)) views
    into a source DataFrame. Each view has a sorted datetime array for fast
    window slicing via numpy.searchsorted.
    """

    def __init__(self, df: pd.DataFrame, key_cols: List[str], time_col: str):
        assert all(k in df.columns for k in key_cols), "key cols missing"
        assert time_col in df.columns, "time col missing"

        self.key_cols = key_cols
        self.time_col = time_col

        # Ensure datetime dtype and drop invalid timestamps
        if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])

        # If timezone-aware, drop tz to compare with naive anchors
        if getattr(df[time_col].dt, "tz", None) is not None:
            df[time_col] = df[time_col].dt.tz_localize(None)

        # If keys are also present as index levels (due to set_index(drop=False)),
        # reset the index to avoid the "both an index level and a column label" ambiguity.
        if isinstance(df.index, pd.MultiIndex):
            if any(k in (df.index.names or []) for k in key_cols):
                df = df.reset_index(drop=True)
        else:
            if df.index.name in key_cols:
                df = df.reset_index(drop=True)

        # Build per-key views with sorted indices and time arrays (datetime64[ns])
        self._views: Dict[Tuple, Tuple[np.ndarray, np.ndarray]] = {}
        # view tuple: (row_index_array, time_datetime64_ns_array)

        for key, sub in df.groupby(key_cols, sort=False):
            if not isinstance(key, tuple):
                key = (key,)
            order = np.argsort(sub[time_col].values.astype("datetime64[ns]"))
            idx = sub.index.values[order]
            tns = sub[time_col].values.astype("datetime64[ns]")[order]
            self._views[key] = (idx, tns)

        self._df = df  # keep reference (already cleaned)

    def keys(self):
        return self._views.keys()

    def slice_window(
        self, key_tuple: Tuple, t0: pd.Timestamp, t1: pd.Timestamp
    ) -> pd.DataFrame:
        """Return rows for key within [t0, t1] using searchsorted."""
        if not isinstance(key_tuple, tuple):
            key_tuple = (key_tuple,)
        view = self._views.get(key_tuple)
        if view is None:
            return self._df.iloc[[]]

        idx, tns = view
        left = np.searchsorted(tns, np.datetime64(t0, "ns"), side="left")
        right = np.searchsorted(tns, np.datetime64(t1, "ns"), side="right")
        if right <= left:
            return self._df.iloc[[]]
        return self._df.loc[idx[left:right]]
