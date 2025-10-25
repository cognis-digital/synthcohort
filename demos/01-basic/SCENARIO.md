# Demo 01 - Basic cohort generation

This demo shows generating a small, reproducible synthetic patient cohort
from a custom schema spec (`vitals_schema.json`).

## What it shows

- Loading and validating a JSON schema with multiple field types
  (`id`, `int`, `choice`, `weighted_choice`, `normal`, `bool`, `date`,
  `first_name`, `last_name`).
- Deterministic generation: the same `--seed` always yields the same rows.
- Two output modes: CSV (default `table`) for spreadsheets and `json` for
  piping into CI or `jq`.

## Run it

```bash
# CSV to stdout (10 patients, reproducible)
python -m synthcohort gen --schema demos/01-basic/vitals_schema.json \
    --count 10 --seed 42

# JSON for piping
python -m synthcohort gen --schema demos/01-basic/vitals_schema.json \
    --count 10 --seed 42 --format json | head

# Validate the schema (exit code 0 == valid, 1 == invalid)
python -m synthcohort validate --schema demos/01-basic/vitals_schema.json
```

## Expected result

- `gen` prints a CSV with a header row plus exactly 10 data rows. The first
  column `patient_id` runs `MRN001000`, `MRN001001`, ... sequentially.
- All values stay within their schema bounds (e.g. `age` in 18-90,
  `systolic_bp` clamped to 70-230).
- Running `gen` twice with `--seed 42` produces byte-identical output.
- `validate` prints `VALID: vitals (8 fields)` and exits 0.
- The data is fully synthetic and contains no real PHI.
