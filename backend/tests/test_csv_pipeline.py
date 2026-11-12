import pandas as pd

from services.csv_pipeline import clean_csv, missing_value_count, verify_csv


def test_cleaner_normalizes_headers_trims_text_and_removes_duplicates(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text(
        " Customer Name , Email Address , Plan \n"
        " Ava Patel , ava@example.com , Pro \n"
        "Ava Patel,ava@example.com,Pro\n"
        "Noah Kim,noah@example.com,Basic\n",
        encoding="utf-8",
    )

    cleaned, report = clean_csv(source)

    assert list(cleaned.columns) == ["customer_name", "email_address", "plan"]
    assert len(cleaned) == 2
    assert report["duplicates_removed"] == 1
    assert report["missing_values_remaining"] == 0
    assert cleaned.iloc[0]["customer_name"] == "Ava Patel"


def test_cleaner_does_not_forward_fill_or_invent_missing_values(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text(
        "name,email,region\n"
        "Ava,ava@example.com,South\n"
        "Noah,,\n",
        encoding="utf-8",
    )

    cleaned, report = clean_csv(source)

    assert cleaned.iloc[1]["email"] == ""
    assert cleaned.iloc[1]["region"] == ""
    assert report["missing_values_remaining"] == 2
    assert missing_value_count(cleaned) == 2


def test_verifier_detects_invalid_email_and_blank_cells(tmp_path):
    output = tmp_path / "cleaned.csv"
    output.write_text(
        "name,email\n"
        "Ava,ava@example.com\n"
        "Noah,noah@invalid\n"
        "Mia,\n",
        encoding="utf-8",
    )

    result = verify_csv(output)

    assert result["invalid_emails"] == 1
    assert result["missing_values"] == 1


def test_csv_import_preserves_literal_na_and_leading_zero_identifiers(tmp_path):
    source = tmp_path / "identifiers.csv"
    source.write_text(
        "postal code,status\n00107,NA\n00042,Active\n,\n",
        encoding="utf-8",
    )

    cleaned, report = clean_csv(source)

    assert cleaned["postal_code"].tolist() == ["00107", "00042"]
    assert cleaned["status"].tolist() == ["NA", "Active"]
    assert report["empty_rows_removed"] == 1
