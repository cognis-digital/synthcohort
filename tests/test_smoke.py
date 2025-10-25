"""Smoke tests for SYNTHCOHORT. No network. Runs against the demo schema."""

import csv
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synthcohort import (  # noqa: E402
    TOOL_NAME,
    TOOL_VERSION,
    SchemaError,
    default_schema,
    generate_cohort,
    load_schema,
    rows_to_csv,
    validate_schema,
)
from synthcohort.cli import main  # noqa: E402

DEMO_SCHEMA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "demos",
    "01-basic",
    "vitals_schema.json",
)


def test_metadata():
    assert TOOL_NAME == "synthcohort"
    assert TOOL_VERSION.count(".") == 2


def test_demo_schema_loads_and_validates():
    schema = load_schema(DEMO_SCHEMA)
    assert schema["name"] == "vitals"
    assert len(schema["fields"]) == 8


def test_generate_count_and_fields():
    schema = load_schema(DEMO_SCHEMA)
    rows = generate_cohort(schema, n=25, seed=7)
    assert len(rows) == 25
    expected = [f["name"] for f in schema["fields"]]
    for row in rows:
        assert list(row.keys()) == expected


def test_determinism():
    schema = load_schema(DEMO_SCHEMA)
    a = generate_cohort(schema, n=50, seed=42)
    b = generate_cohort(schema, n=50, seed=42)
    assert a == b
    c = generate_cohort(schema, n=50, seed=43)
    assert a != c  # different seed -> different data


def test_bounds_respected():
    schema = load_schema(DEMO_SCHEMA)
    rows = generate_cohort(schema, n=500, seed=1)
    for row in rows:
        assert 18 <= row["age"] <= 90
        assert 70 <= row["systolic_bp"] <= 230
        assert row["sex"] in ("M", "F")
        assert row["risk_group"] in ("low", "moderate", "high")
        assert isinstance(row["on_statin"], bool)


def test_sequential_ids():
    schema = load_schema(DEMO_SCHEMA)
    rows = generate_cohort(schema, n=5, seed=0)
    ids = [r["patient_id"] for r in rows]
    assert ids == ["MRN001000", "MRN001001", "MRN001002", "MRN001003", "MRN001004"]


def test_weighted_choice_distribution():
    schema = load_schema(DEMO_SCHEMA)
    rows = generate_cohort(schema, n=2000, seed=11)
    counts = {"low": 0, "moderate": 0, "high": 0}
    for row in rows:
        counts[row["risk_group"]] += 1
    # 'low' weighted 60 vs 'high' weighted 10 -> low must dominate high.
    assert counts["low"] > counts["high"]
    assert counts["low"] > counts["moderate"]


def test_default_schema_generates():
    rows = generate_cohort(default_schema(), n=10, seed=5)
    assert len(rows) == 10
    assert "blood_type" in rows[0]


def test_csv_roundtrip():
    rows = generate_cohort(load_schema(DEMO_SCHEMA), n=8, seed=3)
    text = rows_to_csv(rows)
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert len(parsed) == 8
    assert parsed[0]["patient_id"] == "MRN001000"


def test_invalid_schema_raises():
    with pytest.raises(SchemaError):
        validate_schema({"fields": []})
    with pytest.raises(SchemaError):
        validate_schema({"fields": [{"name": "x", "type": "bogus"}]})
    with pytest.raises(SchemaError):
        validate_schema(
            {"fields": [{"name": "a", "type": "int", "min": 10, "max": 1}]}
        )


def test_cli_gen_csv(capsys):
    rc = main(["gen", "--schema", DEMO_SCHEMA, "--count", "3", "--seed", "42"])
    assert rc == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines[0].startswith("patient_id,")
    assert len(lines) == 4  # header + 3 rows


def test_cli_gen_json(capsys):
    rc = main(
        ["--format", "json", "gen", "--schema", DEMO_SCHEMA, "--count", "4",
         "--seed", "42"]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list) and len(data) == 4


def test_cli_validate_pass(capsys):
    rc = main(["validate", "--schema", DEMO_SCHEMA])
    assert rc == 0
    assert "VALID" in capsys.readouterr().out


def test_cli_validate_fail_nonzero(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"fields": [{"name": "x", "type": "nope"}]}))
    rc = main(["validate", "--schema", str(bad)])
    assert rc == 1  # CI gate: invalid schema exits non-zero


def test_cli_validate_fail_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    rc = main(["--format", "json", "validate", "--schema", str(bad)])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False


def test_cli_schema_template(capsys):
    rc = main(["--format", "json", "schema"])
    assert rc == 0
    schema = json.loads(capsys.readouterr().out)
    validate_schema(schema)  # the emitted template must itself be valid
