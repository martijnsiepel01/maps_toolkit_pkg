# tests/analyze/test_utils.py
from maps_toolkit.analyze.utils import get_nested, load_treatments
import json, tempfile, os

def test_get_nested_simple():
    d = {"a": {"b": {"c": 42}}}
    assert get_nested(d, "a.b.c") == 42

def test_get_nested_list_index():
    d = {"prescriptions": [{"name": "amox"}, {"name": "cipro"}]}
    assert get_nested(d, "prescriptions.0.name") == "amox"
    assert get_nested(d, "prescriptions.1.name") == "cipro"

def test_get_nested_missing_key():
    d = {"a": 1}
    assert get_nested(d, "a.b.c") is None

def test_get_nested_out_of_bounds_list():
    d = {"items": [1, 2]}
    assert get_nested(d, "items.5") is None

def test_load_treatments_flattens_hierarchy():
    data = {
        "p1": {
            "admissions": [
                {
                    "patient_contact_id": "adm1",
                    "treatments": [
                        {"treatment_id": "t1", "treatment_start": "2023-01-01"}
                    ],
                }
            ]
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp_path = f.name
    try:
        treatments = load_treatments(tmp_path)
        assert len(treatments) == 1
        t = treatments[0]
        assert t["treatment_id"] == "t1"
        assert t["patient_id"] == "p1"
        assert t["patient_contact_id"] == "adm1"
    finally:
        os.unlink(tmp_path)
