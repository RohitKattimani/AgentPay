"""Shared, conservative CSV normalization and quality checks."""

import re
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
COLUMN_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def read_csv(path: str | Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("The uploaded CSV is empty or has no header row.") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("The uploaded CSV must use UTF-8 text encoding.") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"The uploaded CSV could not be parsed: {exc}") from exc

    if len(frame.columns) == 0:
        raise ValueError("The uploaded CSV must contain at least one column.")
    if len(frame.columns) > 500:
        raise ValueError("The uploaded CSV contains too many columns (maximum: 500).")
    if len(frame) > 250_000:
        raise ValueError("The uploaded CSV contains too many rows (maximum: 250,000).")
    return frame


def normalize_column_names(columns) -> list[str]:
    normalized: list[str] = []
    used: set[str] = set()
    for index, raw_name in enumerate(columns, start=1):
        name = re.sub(r"[^a-z0-9]+", "_", str(raw_name).strip().lower()).strip("_")
        if not name:
            name = f"column_{index}"
        candidate = name
        suffix = 2
        while candidate in used:
            candidate = f"{name}_{suffix}"
            suffix += 1
        used.add(candidate)
        normalized.append(candidate)
    return normalized


def trim_text(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )
    return result


def missing_value_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    count = int(frame.isna().sum().sum())
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        count += int(frame[column].map(lambda value: isinstance(value, str) and not value.strip()).sum())
    return count


def invalid_email_count(frame: pd.DataFrame) -> Tuple[int, int]:
    email_columns = [column for column in frame.columns if "email" in str(column).lower()]
    invalid = 0
    inspected = 0
    for column in email_columns:
        for value in frame[column].tolist():
            if pd.isna(value) or (isinstance(value, str) and not value.strip()):
                continue
            inspected += 1
            if not EMAIL_PATTERN.fullmatch(str(value).strip()):
                invalid += 1
    return invalid, inspected


def formatting_error_count(frame: pd.DataFrame) -> int:
    errors = sum(1 for column in frame.columns if not COLUMN_PATTERN.fullmatch(str(column)))
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        errors += sum(
            1
            for value in frame[column].tolist()
            if isinstance(value, str) and value != value.strip()
        )
    return errors


def clean_csv(path: str | Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    frame = read_csv(path)
    original_rows = len(frame)
    original_columns = len(frame.columns)

    frame.columns = normalize_column_names(frame.columns)
    frame = trim_text(frame)

    empty_cells = frame.isna() | frame.eq("")
    empty_rows = empty_cells.all(axis=1)
    completely_empty_rows = int(empty_rows.sum())
    if completely_empty_rows:
        frame = frame.loc[~empty_rows]

    rows_before_deduplication = len(frame)
    frame = frame.drop_duplicates(keep="first").reset_index(drop=True)
    duplicates_removed = rows_before_deduplication - len(frame)

    invalid_emails, emails_inspected = invalid_email_count(frame)
    report = {
        "original_rows": int(original_rows),
        "output_rows": int(len(frame)),
        "original_columns": int(original_columns),
        "columns_standardized": int(len(frame.columns)),
        "empty_rows_removed": completely_empty_rows,
        "duplicates_removed": int(duplicates_removed),
        "missing_values_remaining": missing_value_count(frame),
        "emails_inspected": emails_inspected,
        "invalid_emails": invalid_emails,
        "cleaning_steps": [
            "Standardized column names to lowercase snake_case",
            "Trimmed leading and trailing whitespace from text cells",
            f"Removed {completely_empty_rows} completely empty rows",
            f"Removed {duplicates_removed} duplicate records",
            "Preserved unresolved values rather than guessing or copying data",
        ],
    }
    return frame, report


def verify_csv(path: str | Path) -> Dict[str, int]:
    frame = read_csv(path)
    invalid_emails, _ = invalid_email_count(frame)
    return {
        "missing_values": missing_value_count(frame),
        "empty_output": int(frame.empty),
        "duplicate_records": int(frame.duplicated().sum()),
        "invalid_emails": invalid_emails,
        "formatting_errors": formatting_error_count(frame),
    }
