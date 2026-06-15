"""Command-line interface for SYNTHCOHORT.

Examples
--------
  # Generate 100 patients using the built-in clinical schema, write CSV
  synthcohort gen --count 100 --seed 42 --out patients.csv

  # Generate from a custom schema file and stream CSV to stdout
  synthcohort gen --schema my_schema.json --count 50

  # Emit JSON (for piping into jq / CI fixtures)
  synthcohort gen --count 10 --format json

  # Validate a schema file without generating (exit 1 if invalid)
  synthcohort validate --schema my_schema.json

  # Print the built-in default schema to use as a starting template
  synthcohort schema
"""

import argparse
import json
import sys

from . import TOOL_NAME, TOOL_VERSION
from .core import (
    SchemaError,
    default_schema,
    generate_cohort,
    load_schema,
    rows_to_csv,
    validate_schema,
)


def _build_parser():
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description=(
            "Generate realistic, PHI-free synthetic patient cohorts from a "
            "schema spec."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  synthcohort gen --count 100 --seed 42 --out patients.csv\n"
            "  synthcohort gen --schema my_schema.json --count 50\n"
            "  synthcohort gen --count 10 --format json | jq '.[0]'\n"
            "  synthcohort validate --schema my_schema.json\n"
            "  synthcohort schema > template.json\n"
        ),
    )
    parser.add_argument(
        "--version", action="version", version="%s %s" % (TOOL_NAME, TOOL_VERSION)
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="output format for commands that print data (default: table)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    gen = sub.add_parser(
        "gen", help="generate a synthetic cohort (CSV by default)"
    )
    gen.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="number of records to generate (default: 10)",
    )
    gen.add_argument(
        "-s",
        "--schema",
        help="path to a JSON schema file (defaults to built-in clinical schema)",
    )
    gen.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible output",
    )
    gen.add_argument(
        "-o",
        "--out",
        help="write output to this file instead of stdout",
    )

    val = sub.add_parser("validate", help="validate a schema file")
    val.add_argument(
        "-s", "--schema", required=True, help="path to a JSON schema file"
    )

    sub.add_parser("schema", help="print the built-in default schema template")

    return parser


def _emit(text, out_path):
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        except OSError as exc:
            sys.stderr.write("error: cannot write output file: %s\n" % exc)
            raise
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def _cmd_gen(args):
    if args.count < 0:
        sys.stderr.write("error: --count must be >= 0\n")
        return 2
    try:
        schema = load_schema(args.schema) if args.schema else default_schema()
        rows = generate_cohort(schema, args.count, seed=args.seed)
    except SchemaError as exc:
        sys.stderr.write("schema error: %s\n" % exc)
        return 1

    try:
        if args.format == "json":
            _emit(json.dumps(rows, indent=2), args.out)
        else:
            # 'table' format for gen means CSV (the tool's native tabular output).
            # Always pass fieldnames so a zero-count run still emits the header.
            fieldnames = [f["name"] for f in schema["fields"]]
            _emit(rows_to_csv(rows, fieldnames=fieldnames), args.out)
    except OSError:
        return 2
    return 0


def _cmd_validate(args):
    try:
        schema = load_schema(args.schema)
    except SchemaError as exc:
        if args.format == "json":
            sys.stdout.write(
                json.dumps({"valid": False, "error": str(exc)}, indent=2) + "\n"
            )
        else:
            sys.stderr.write("INVALID: %s\n" % exc)
        return 1

    n_fields = len(schema["fields"])
    if args.format == "json":
        sys.stdout.write(
            json.dumps(
                {"valid": True, "name": schema.get("name"), "fields": n_fields},
                indent=2,
            )
            + "\n"
        )
    else:
        sys.stdout.write(
            "VALID: %s (%d fields)\n" % (schema.get("name", "<unnamed>"), n_fields)
        )
    return 0


def _cmd_schema(args):
    schema = default_schema()
    if args.format == "json":
        sys.stdout.write(json.dumps(schema, indent=2) + "\n")
    else:
        # table view: list fields and their types
        validate_schema(schema)
        lines = ["%-16s %s" % ("FIELD", "TYPE"), "%-16s %s" % ("-" * 16, "-" * 16)]
        for f in schema["fields"]:
            lines.append("%-16s %s" % (f["name"], f["type"]))
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command is None:
            parser.print_help()
            return 0
        if args.command == "gen":
            return _cmd_gen(args)
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "schema":
            return _cmd_schema(args)
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("internal error: %s\n" % exc)
        return 3

    parser.print_help()
    return 2
