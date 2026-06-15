"""SYNTHCOHORT MCP server — exposes generate_cohort() as an MCP tool."""
from __future__ import annotations

import json

from synthcohort.core import (
    SchemaError,
    default_schema,
    generate_cohort,
    validate_schema,
)


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-synthcohort[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import]
    except Exception:
        print("Install the MCP extra: pip install 'cognis-synthcohort[mcp]'")
        return 1
    app = FastMCP("synthcohort")

    @app.tool()
    def synthcohort_gen(  # noqa: E501
        schema_json: str, count: int = 10, seed: int | None = None
    ) -> str:
        """Generate a synthetic patient cohort from a JSON schema string.

        Returns a JSON array of records, or a JSON error object on bad input.
        """
        try:
            schema = json.loads(schema_json) if schema_json else default_schema()
            validate_schema(schema)
            rows = generate_cohort(schema, max(0, int(count)), seed=seed)
            return json.dumps(rows)
        except (SchemaError, ValueError, TypeError) as exc:
            return json.dumps({"error": str(exc)})

    app.run()
    return 0
