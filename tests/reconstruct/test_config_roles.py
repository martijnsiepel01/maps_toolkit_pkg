import pytest
from maps_toolkit.reconstruct.core.config_loader import get_source_role, validate_config

MINIMAL_CONFIG = {
    "data_sources": {
        "prescriptions": {
            "enabled": True,
            "role": "prescriptions",
            "file_path": "data/processed/prescriptions.txt",
            "columns": {
                "required": {
                    "patient_id": "PSEUDO_ID",
                    "patient_contact_id": "PATIENTCONTACTID",
                    "start_datetime": "STARTDATUMTIJD",
                    "stop_datetime": "STOPDATUMTIJD",
                    "medication_name": "MEDICATIESTOFNAAM",
                }
            },
        },
        "admissions": {
            "enabled": True,
            "role": "admissions",
            "file_path": "data/processed/admissions.txt",
            "columns": {
                "required": {
                    "patient_id": "PSEUDO_ID",
                    "patient_contact_id": "PATIENTCONTACTID",
                    "admission_start": "OPNAMEDATUM",
                    "admission_end": "ONTSLAGDATUM",
                }
            },
        },
    }
}


def test_prescriptions_role():
    assert get_source_role(MINIMAL_CONFIG, "prescriptions") == "prescriptions"


def test_admissions_role():
    assert get_source_role(MINIMAL_CONFIG, "admissions") == "admissions"


def test_validate_config_passes_minimal():
    validate_config(MINIMAL_CONFIG)


def test_validate_config_missing_prescriptions_raises():
    cfg = {"data_sources": {}}
    with pytest.raises(Exception):
        validate_config(cfg)
