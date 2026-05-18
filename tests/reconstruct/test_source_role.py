import pytest
from maps_toolkit.reconstruct.core.config_loader import get_source_role, find_source_by_role

def _make_cfg(sources: dict) -> dict:
    return {"data_sources": sources}

def test_prescriptions_role():
    cfg = _make_cfg({"prescriptions": {
        "enabled": True, "role": "prescriptions", "file_path": "x.txt",
        "columns": {"required": {"patient_id": "A", "patient_contact_id": "B",
                                  "start_datetime": "C", "stop_datetime": "D",
                                  "medication_name": "E"}}
    }})
    assert get_source_role(cfg, "prescriptions") == "prescriptions"

def test_admissions_role():
    cfg = _make_cfg({"admissions": {
        "enabled": True, "role": "admissions", "file_path": "x.txt",
        "columns": {"required": {"patient_id": "A", "patient_contact_id": "B",
                                  "admission_start": "C", "admission_end": "D"}},
        "match": {"on": ["patient_id", "patient_contact_id"]}
    }})
    assert get_source_role(cfg, "admissions") == "admissions"

def test_treatment_level_role():
    cfg = _make_cfg({"cultures": {
        "enabled": True, "role": "treatment_level", "file_path": "x.txt",
        "columns": {"required": {"patient_id": "A", "sample_datetime": "B",
                                  "material_category": "C"}},
        "match": {"on": ["patient_id"],
                  "time_window": {"column": "sample_datetime",
                                  "before_hours": 72, "after_hours": "until_end"}}
    }})
    assert get_source_role(cfg, "cultures") == "treatment_level"

def test_patient_level_role():
    cfg = _make_cfg({"patients": {
        "enabled": True, "role": "patient_level", "file_path": "x.csv",
        "columns": {"required": {"patient_id": "patientID_pseudo"},
                    "optional": {"groep": "groep"}},
        "nest_as": "esbl"
    }})
    assert get_source_role(cfg, "patients") == "patient_level"

def test_missing_role_raises():
    cfg = _make_cfg({"some_source": {
        "enabled": True, "file_path": "x.txt",
        "columns": {"required": {"patient_id": "A"}}
    }})
    with pytest.raises(KeyError):
        get_source_role(cfg, "some_source")

def test_find_source_by_role_admissions():
    cfg = _make_cfg({"admissions": {
        "enabled": True, "role": "admissions", "file_path": "x.txt",
        "columns": {"required": {"patient_id": "A", "patient_contact_id": "B",
                                  "admission_start": "C", "admission_end": "D"}},
        "match": {"on": ["patient_id", "patient_contact_id"]}
    }})
    assert find_source_by_role(cfg, "admissions") == "admissions"

def test_find_source_by_role_missing_returns_none():
    cfg = _make_cfg({"prescriptions": {
        "enabled": True, "role": "prescriptions", "file_path": "x.txt",
        "columns": {"required": {"patient_id": "A", "patient_contact_id": "B",
                                  "start_datetime": "C", "stop_datetime": "D",
                                  "medication_name": "E"}}
    }})
    assert find_source_by_role(cfg, "admissions") is None

def test_find_source_by_role_skips_disabled():
    cfg = _make_cfg({
        "admissions": {
            "enabled": False, "role": "admissions", "file_path": "x.txt",
            "columns": {"required": {"patient_id": "A", "patient_contact_id": "B",
                                      "admission_start": "C", "admission_end": "D"}},
            "match": {"on": ["patient_id", "patient_contact_id"]}
        }
    })
    assert find_source_by_role(cfg, "admissions") is None
