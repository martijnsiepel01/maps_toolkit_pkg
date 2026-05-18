# utils.py
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

def parse_datetime(date_string: Any) -> Optional[datetime]:
    if not isinstance(date_string, str):
        return None
    try:
        return pd.to_datetime(date_string)
    except (ValueError, TypeError):
        return None

def load_and_flatten_data(path: str) -> List[Dict[str, Any]]:
    """
    Loads the nested JSON from the ATMT-Reconstruct tool and flattens it
    into a list of treatment episodes.

    Each item in the returned list is a dictionary representing one treatment,
    enriched with parent-level info (from the patient and admission).
    """
    print(f"Loading data from: {path}...")
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    treatment_rows = []
    for patient_id, patient_data in data.items():
        # Copy all top-level patient info, excluding the 'admissions' list
        patient_context = {k: v for k, v in patient_data.items() if k != 'admissions'}

        for admission in patient_data.get('admissions', []):
            # Copy admission-level info, excluding 'treatments'
            admission_context = {k: v for k, v in admission.items() if k != 'treatments'}

            for treatment in admission.get('treatments', []):
                # Combine all levels of context with the treatment info
                # The order is important: treatment keys will overwrite admission/patient keys if they conflict
                row = {**patient_context, **admission_context, **treatment}
                treatment_rows.append(row)

    print(f"Successfully loaded and flattened {len(treatment_rows)} treatment episodes.")
    return treatment_rows


def get_nested(obj, path: str):
    """Navigate a dot-separated path in nested dicts/lists. '0' is a list index."""
    for part in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (IndexError, ValueError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def load_treatments(path: str) -> list:
    """
    Load the reconstruct JSON and return a flat list of treatment dicts.
    Each treatment is enriched with patient_id and patient_contact_id from parent levels.
    Supports both JSON structures: top-level dict (old) and {"patients": [...]} (new).
    """
    print(f"Loading treatments from: {path}...")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, dict) and "patients" in data:
        patient_iter = ((p["patient_id"], p) for p in data["patients"])
    else:
        patient_iter = data.items()

    rows = []
    for patient_id, patient_data in patient_iter:
        patient_ctx = {k: v for k, v in patient_data.items() if k not in ("admissions", "patient_id")}
        for admission in patient_data.get("admissions", []):
            adm_ctx = {k: v for k, v in admission.items() if k != "treatments"}
            for treatment in admission.get("treatments", []):
                row = {"patient_id": patient_id, **patient_ctx, **adm_ctx, **treatment}
                rows.append(row)

    print(f"Loaded {len(rows)} treatment episodes.")
    return rows