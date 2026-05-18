# plugins/shared.py
from maps_toolkit.analyze.utils import parse_datetime
from datetime import datetime
from typing import Optional   # ✅ add this
import ast

def year_month(treatment_row: dict, params: dict) -> Optional[str]:
    """Returns the year and month ('YYYY-MM') from a date field."""
    date_field = params.get('date_field')
    if not date_field:
        raise ValueError("'date_field' must be provided in params.")
    dt = parse_datetime(treatment_row.get(date_field))
    return dt.strftime('%Y-%m') if dt else None

def _parse_indication_list(answer_str: str) -> list:
    """Safely evaluates a string that looks like a list."""
    try:
        # ast.literal_eval is safer than eval()
        parsed_list = ast.literal_eval(answer_str)
        if isinstance(parsed_list, list):
            return parsed_list
    except (ValueError, SyntaxError):
        # Fallback for simple strings
        return [answer_str]
    return []

def _parse_answers(answer_list: list) -> dict:
    """
    This is your parsing function, slightly adapted to work on a list of strings.
    It extracts the clinical 'locatie' (indication).
    """
    answer_str = ", ".join(answer_list) # Join list into a single string for parsing
    
    locatie_options = {
        "Bot/gewicht", "CZS", "Gastro-enteritis", "Gist/schimmelinfectie",
        "Gynaecologische infectie", "Huid/weke delen", "Intra-abdominale infectie",
        "KNO-gebied of mond", "Koorts bij neutropenie", "Lijninfectie", "Luchtwegen",
        "Mediastinum", "Oog", "S. aureus bacteriemie", "Urineweginfectie",
        "Onbekend/Sepsis eci", "Overig, namelijk:" # Note: corrected your original typo 'Overig/ namelijk:'
    }
    
    # We only need the 'locatie' for this analysis
    locatie_answer = []
    for option in locatie_options:
        # Check for whole word match to avoid partial matches (e.g., 'Oog' in 'Gynaecologische')
        if option in answer_str:
            locatie_answer.append(option)
    
    # Prioritize a clinical location over generic terms
    clinical_locations = [loc for loc in locatie_answer if loc != "Overig, namelijk:"]
    
    if clinical_locations:
        # If we find one or more, we'll use the first one found.
        # This is the most likely candidate for the true indication.
        return clinical_locations[0]
        
    return "Unknown" # Fallback if no specific location is found

def first_prescription_value(treatment_row: dict, params: dict) -> str:
    """
    Finds the first prescription and returns the RAW value of a specified field.
    """
    # ... (this function is unchanged) ...
    value_field = params.get('value_field')
    start_field = params.get('start_field', 'start_datetime')
    fallback = params.get('fallback', 'Unknown')

    if not value_field:
        raise ValueError("'value_field' must be provided in params.")

    prescriptions = treatment_row.get('prescriptions', [])
    if not prescriptions:
        return fallback

    first_rx = min(
        prescriptions,
        key=lambda rx: parse_datetime(rx.get(start_field)) or datetime.max
    )
    return first_rx.get(value_field, fallback)


def get_clinical_indication(treatment_row: dict, params: dict) -> str:
    """
    New plugin that gets the raw indication string from the first prescription,
    then uses the parser to find the true clinical indication ('locatie').
    """
    # Step 1: Get the raw indication string (which is a list-as-a-string)
    raw_indication_str = first_prescription_value(treatment_row, params)
    
    # Step 2: Safely convert the string "['item1', 'item2']" into a Python list
    indication_list = _parse_indication_list(raw_indication_str)
    
    # Step 3: Use the parser to extract the clinical indication
    clinical_indication = _parse_answers(indication_list)
    
    return clinical_indication


def year(treatment_row: dict, params: dict) -> Optional[str]:
    """Returns the year ('YYYY') from a date field."""
    date_field = params.get('date_field')
    if not date_field:
        raise ValueError("'date_field' must be provided in params.")
    dt = parse_datetime(treatment_row.get(date_field))
    return str(dt.year) if dt else None


def numeric_flag(treatment_row: dict, params: dict) -> int:
    """Return 1 if a numeric value exceeds a threshold, else 0.

    Params:
      source: numeric value (typically via '@properties.some_count')
      threshold: comparison threshold (default 0)
    """
    source = params.get("source")
    threshold = params.get("threshold", 0)
    try:
        return 1 if float(source) > float(threshold) else 0
    except (TypeError, ValueError):
        return 0


def prescription_count(treatment_row: dict, params: dict) -> int:
    """Return the number of prescriptions in this treatment episode."""
    prescriptions = treatment_row.get("prescriptions")
    return len(prescriptions) if isinstance(prescriptions, list) else 0


def dict_get(treatment_row: dict, params: dict):
    """
    Generic helper to extract a value from a dict-like property.

    Params:
      source: object (typically provided via '@properties.some_dict')
      key: key to extract from the dict
      default: value to return if key missing or source not a dict (default: None)
    """
    source = params.get("source")
    key = params.get("key")
    default = params.get("default", None)
    if not key:
        raise ValueError("'key' must be provided in params.")
    if isinstance(source, dict):
        return source.get(key, default)
    return default
