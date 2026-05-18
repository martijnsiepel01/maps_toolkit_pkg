import pandas as pd
from maps_toolkit.analyze.plugins.duration import by_group, values_by_group
from maps_toolkit.analyze.plugins.aggregate import select


SAMPLE_TREATMENTS = [
    {
        "treatment_start": "2023-01-01T08:00:00",
        "treatment_end": "2023-01-05T08:00:00",
        "prescriptions": [{"group_admission": "Internal Medicine"}],
    },
    {
        "treatment_start": "2023-01-10T08:00:00",
        "treatment_end": "2023-01-15T08:00:00",
        "prescriptions": [{"group_admission": "Surgery"}],
    },
]


def test_by_group_returns_dataframe():
    result = by_group(SAMPLE_TREATMENTS, {
        "group_field": "prescriptions.0.group_admission",
        "start_field": "treatment_start",
        "end_field": "treatment_end",
        "aggregations": ["count", "median"],
    })
    assert isinstance(result, pd.DataFrame)
    assert len(result) > 0


def test_values_by_group_returns_dataframe():
    result = values_by_group(SAMPLE_TREATMENTS, {
        "group_field": "prescriptions.0.group_admission",
        "start_field": "treatment_start",
        "end_field": "treatment_end",
    })
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2


def test_select_returns_dataframe():
    result = select(SAMPLE_TREATMENTS, {
        "fields": [
            {"name": "start", "path": "treatment_start"},
            {"name": "end", "path": "treatment_end"},
        ]
    })
    assert isinstance(result, pd.DataFrame)
    assert "start" in result.columns
