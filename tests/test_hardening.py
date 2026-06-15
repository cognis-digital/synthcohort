"""Hardening tests: edge cases, bad input, and error paths for SYNTHCOHORT."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthcohort.core import (  # noqa: E402
    SchemaError,
    generate_cohort,
    rows_to_csv,
    validate_schema,
)
from synthcohort.cli import main  # noqa: E402


# ---------------------------------------------------------------------------
# core.py: validate_schema edge cases
# ---------------------------------------------------------------------------


def test_validate_schema_none_raises():
    """None schema must raise SchemaError, not AttributeError."""
    with pytest.raises(SchemaError, match="None"):
        validate_schema(None)


def test_validate_schema_not_dict_raises():
    with pytest.raises(SchemaError, match="JSON object"):
        validate_schema(["not", "a", "dict"])


def test_validate_schema_empty_fields_raises():
    """An empty fields list must be rejected."""
    with pytest.raises(SchemaError):
        validate_schema({"fields": []})


def test_validate_schema_duplicate_field_name():
    schema = {
        "fields": [
            {"name": "age", "type": "int", "min": 0, "max": 99},
            {"name": "age", "type": "int", "min": 0, "max": 50},
        ]
    }
    with pytest.raises(SchemaError, match="duplicate"):
        validate_schema(schema)


def test_validate_schema_all_zero_weights():
    """weighted_choice with all-zero weights must be rejected before generation."""
    schema = {
        "fields": [
            {
                "name": "grp",
                "type": "weighted_choice",
                "values": ["a", "b"],
                "weights": [0, 0],
            }
        ]
    }
    with pytest.raises(SchemaError, match="zero"):
        validate_schema(schema)


def test_validate_schema_weights_wrong_length():
    schema = {
        "fields": [
            {
                "name": "grp",
                "type": "weighted_choice",
                "values": ["a", "b", "c"],
                "weights": [1, 2],  # length mismatch
            }
        ]
    }
    with pytest.raises(SchemaError, match="weights length"):
        validate_schema(schema)


def test_validate_schema_date_start_after_end():
    schema = {
        "fields": [
            {
                "name": "dt",
                "type": "date",
                "start": "2025-12-31",
                "end": "2025-01-01",
            }
        ]
    }
    with pytest.raises(SchemaError, match="start after end"):
        validate_schema(schema)


def test_validate_schema_normal_negative_sd():
    schema = {
        "fields": [
            {"name": "bp", "type": "normal", "mean": 120, "sd": -1}
        ]
    }
    with pytest.raises(SchemaError, match="negative sd"):
        validate_schema(schema)


# ---------------------------------------------------------------------------
# core.py: rows_to_csv edge cases
# ---------------------------------------------------------------------------


def test_rows_to_csv_empty_rows_returns_empty_string():
    """Empty rows with no fieldnames must not crash — returns empty string."""
    result = rows_to_csv([])
    assert result == ""


def test_rows_to_csv_empty_rows_with_fieldnames_returns_header():
    """Empty rows with explicit fieldnames must still produce a header row."""
    result = rows_to_csv([], fieldnames=["id", "age"])
    assert result.strip() == "id,age"


# ---------------------------------------------------------------------------
# core.py: generate_cohort edge cases
# ---------------------------------------------------------------------------


def test_generate_cohort_zero_count():
    from synthcohort.core import default_schema
    rows = generate_cohort(default_schema(), n=0, seed=1)
    assert rows == []


def test_generate_cohort_negative_raises():
    from synthcohort.core import default_schema
    with pytest.raises(ValueError, match=">= 0"):
        generate_cohort(default_schema(), n=-1)


# ---------------------------------------------------------------------------
# cli.py: missing file -> non-zero exit
# ---------------------------------------------------------------------------


def test_cli_gen_missing_schema_file(capsys):
    rc = main(["gen", "--schema", "/nonexistent/path/schema.json", "--count", "1"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "schema" in err.lower() or "error" in err.lower()


def test_cli_validate_missing_schema_file(capsys):
    rc = main(["validate", "--schema", "/nonexistent/path/schema.json"])
    assert rc != 0


def test_cli_validate_malformed_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json at all")
    rc = main(["validate", "--schema", str(bad)])
    assert rc == 1
    err = capsys.readouterr().err
    assert err  # must print something to stderr


def test_cli_gen_bad_output_path(tmp_path, capsys):
    """Writing to a directory (not a file) must return non-zero, not traceback."""
    rc = main([
        "gen", "--count", "5", "--seed", "1",
        "--out", str(tmp_path),  # tmp_path is a directory -> OSError
    ])
    assert rc != 0


def test_cli_gen_zero_count(capsys):
    rc = main(["gen", "--count", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    # Only the CSV header line (no data rows)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("patient_id,")


def test_cli_gen_negative_count(capsys):
    rc = main(["gen", "--count", "-1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--count" in err


# ---------------------------------------------------------------------------
# mcp_server.py: compiles and imports without crashing
# ---------------------------------------------------------------------------


def test_mcp_server_imports():
    """mcp_server must import cleanly (no NameError for missing scan/to_json)."""
    import importlib
    mod = importlib.import_module("synthcohort.mcp_server")
    assert callable(mod.serve)
