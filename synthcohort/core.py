"""Core engine for SYNTHCOHORT.

Generates realistic, internally-consistent synthetic patient cohorts from a
JSON schema spec. Standard library only. Fully deterministic given a seed so
generated cohorts are reproducible for CI test fixtures.

A schema is a dict:
    {
      "name": "my_cohort",
      "fields": [
        {"name": "patient_id", "type": "id", "prefix": "PT"},
        {"name": "age",        "type": "int", "min": 0, "max": 95},
        {"name": "sex",        "type": "choice", "values": ["M", "F"]},
        {"name": "weight_kg",  "type": "float", "min": 3.0, "max": 140.0,
                                "decimals": 1},
        {"name": "systolic",   "type": "normal", "mean": 120, "sd": 15,
                                "min": 70, "max": 220},
        {"name": "diabetic",   "type": "bool", "p": 0.1},
        {"name": "first_name", "type": "first_name"},
        {"name": "last_name",  "type": "last_name"},
        {"name": "enrolled",   "type": "date", "start": "2020-01-01",
                                "end": "2024-12-31"}
      ]
    }

Supported field types are listed in SUPPORTED_TYPES.
"""

import csv
import datetime as _dt
import io
import json
import random

SUPPORTED_TYPES = (
    "id",
    "int",
    "float",
    "normal",
    "bool",
    "choice",
    "weighted_choice",
    "first_name",
    "last_name",
    "date",
)

# Small, license-free name pools. Enough variety for realistic test data
# without shipping a megabyte of dictionaries.
_FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Carlos", "Maria", "Wei",
    "Aisha", "Omar", "Priya", "Kenji", "Fatima", "Diego", "Ingrid",
    "Hassan", "Mei", "Lucas", "Sofia", "Noah", "Olivia", "Liam", "Emma",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Lee", "Chen",
    "Patel", "Nguyen", "Kim", "Singh", "Khan", "Okafor", "Yamamoto",
    "Ivanov", "Mueller", "Rossi", "Andersson", "Haddad",
]

_EPOCH = _dt.date(1970, 1, 1)


class SchemaError(ValueError):
    """Raised when a schema spec is malformed or unsupported."""


def default_schema():
    """Return a ready-to-use clinical patient cohort schema."""
    return {
        "name": "patients",
        "fields": [
            {"name": "patient_id", "type": "id", "prefix": "PT", "width": 6},
            {"name": "first_name", "type": "first_name"},
            {"name": "last_name", "type": "last_name"},
            {"name": "age", "type": "int", "min": 0, "max": 95},
            {"name": "sex", "type": "choice", "values": ["M", "F"]},
            {
                "name": "blood_type",
                "type": "weighted_choice",
                "values": ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"],
                "weights": [37, 36, 8, 3, 7, 6, 2, 1],
            },
            {
                "name": "height_cm",
                "type": "normal",
                "mean": 168,
                "sd": 11,
                "min": 50,
                "max": 210,
                "decimals": 1,
            },
            {
                "name": "weight_kg",
                "type": "normal",
                "mean": 78,
                "sd": 16,
                "min": 3,
                "max": 200,
                "decimals": 1,
            },
            {
                "name": "systolic_bp",
                "type": "normal",
                "mean": 124,
                "sd": 16,
                "min": 70,
                "max": 230,
            },
            {"name": "diabetic", "type": "bool", "p": 0.11},
            {
                "name": "enrolled_date",
                "type": "date",
                "start": "2021-01-01",
                "end": "2024-12-31",
            },
        ],
    }


def load_schema(path):
    """Load and validate a schema from a JSON file path."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except json.JSONDecodeError as exc:
        raise SchemaError("schema file is not valid JSON: %s" % exc) from exc
    except OSError as exc:
        raise SchemaError("cannot read schema file: %s" % exc) from exc
    validate_schema(schema)
    return schema


def validate_schema(schema):
    """Validate a schema dict in place. Raise SchemaError on problems.

    Returns the schema unchanged so it can be used inline.
    """
    if not isinstance(schema, dict):
        raise SchemaError("schema must be a JSON object")
    fields = schema.get("fields")
    if not isinstance(fields, list) or not fields:
        raise SchemaError("schema must contain a non-empty 'fields' list")

    seen = set()
    for idx, field in enumerate(fields):
        if not isinstance(field, dict):
            raise SchemaError("field #%d must be an object" % idx)
        fname = field.get("name")
        if not fname or not isinstance(fname, str):
            raise SchemaError("field #%d is missing a string 'name'" % idx)
        if fname in seen:
            raise SchemaError("duplicate field name: %r" % fname)
        seen.add(fname)
        ftype = field.get("type")
        if ftype not in SUPPORTED_TYPES:
            raise SchemaError(
                "field %r has unsupported type %r (supported: %s)"
                % (fname, ftype, ", ".join(SUPPORTED_TYPES))
            )
        _validate_field_params(field, ftype)
    return schema


def _validate_field_params(field, ftype):
    name = field["name"]

    def _num(key):
        val = field.get(key)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise SchemaError("field %r requires numeric %r" % (name, key))
        return val

    if ftype in ("int", "float"):
        lo, hi = _num("min"), _num("max")
        if lo > hi:
            raise SchemaError("field %r has min > max" % name)
    elif ftype == "normal":
        _num("mean")
        sd = _num("sd")
        if sd < 0:
            raise SchemaError("field %r has negative sd" % name)
    elif ftype == "bool":
        p = field.get("p", 0.5)
        if not isinstance(p, (int, float)) or not (0.0 <= p <= 1.0):
            raise SchemaError("field %r 'p' must be in [0, 1]" % name)
    elif ftype in ("choice", "weighted_choice"):
        values = field.get("values")
        if not isinstance(values, list) or not values:
            raise SchemaError("field %r requires a non-empty 'values' list" % name)
        if ftype == "weighted_choice":
            weights = field.get("weights")
            if weights is not None:
                if len(weights) != len(values):
                    raise SchemaError(
                        "field %r weights length != values length" % name
                    )
                if any((not isinstance(w, (int, float))) or w < 0 for w in weights):
                    raise SchemaError(
                        "field %r weights must be non-negative numbers" % name
                    )
    elif ftype == "date":
        for key in ("start", "end"):
            try:
                _dt.date.fromisoformat(field[key])
            except (KeyError, ValueError) as exc:
                raise SchemaError(
                    "field %r needs ISO 'start'/'end' dates" % name
                ) from exc
        if _dt.date.fromisoformat(field["start"]) > _dt.date.fromisoformat(
            field["end"]
        ):
            raise SchemaError("field %r has start after end" % name)


def _gen_value(field, rng, row_index):
    ftype = field["type"]

    if ftype == "id":
        prefix = field.get("prefix", "ID")
        width = int(field.get("width", 6))
        start = int(field.get("start", 1))
        return "%s%0*d" % (prefix, width, start + row_index)

    if ftype == "int":
        return rng.randint(int(field["min"]), int(field["max"]))

    if ftype == "float":
        decimals = int(field.get("decimals", 2))
        val = rng.uniform(float(field["min"]), float(field["max"]))
        return round(val, decimals)

    if ftype == "normal":
        decimals = field.get("decimals")
        val = rng.gauss(float(field["mean"]), float(field["sd"]))
        if "min" in field:
            val = max(val, float(field["min"]))
        if "max" in field:
            val = min(val, float(field["max"]))
        if decimals is None:
            return int(round(val))
        return round(val, int(decimals))

    if ftype == "bool":
        p = float(field.get("p", 0.5))
        return rng.random() < p

    if ftype == "choice":
        return rng.choice(field["values"])

    if ftype == "weighted_choice":
        values = field["values"]
        weights = field.get("weights")
        if weights is None:
            return rng.choice(values)
        return rng.choices(values, weights=weights, k=1)[0]

    if ftype == "first_name":
        return rng.choice(_FIRST_NAMES)

    if ftype == "last_name":
        return rng.choice(_LAST_NAMES)

    if ftype == "date":
        start = _dt.date.fromisoformat(field["start"])
        end = _dt.date.fromisoformat(field["end"])
        span = (end - start).days
        offset = rng.randint(0, span)
        return (start + _dt.timedelta(days=offset)).isoformat()

    raise SchemaError("unsupported type %r" % ftype)


def generate_record(schema, rng, row_index):
    """Generate a single record (ordered dict) from the schema.

    rng must be a random.Random instance; row_index is the 0-based row number
    used by sequential id fields.
    """
    record = {}
    for field in schema["fields"]:
        record[field["name"]] = _gen_value(field, rng, row_index)
    return record


def generate_cohort(schema, n, seed=None):
    """Generate a list of n synthetic records from the schema.

    Deterministic for a given (schema, n, seed). Validates the schema first.
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    validate_schema(schema)
    rng = random.Random(seed)
    return [generate_record(schema, rng, i) for i in range(n)]


def rows_to_csv(rows, fieldnames=None):
    """Serialize a list of record dicts to a CSV string."""
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()
