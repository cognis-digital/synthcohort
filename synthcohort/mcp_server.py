"""SYNTHCOHORT MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from synthcohort.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-synthcohort[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-synthcohort[mcp]'")
        return 1
    app = FastMCP("synthcohort")

    @app.tool()
    def synthcohort_scan(target: str) -> str:
        """Generate statistically realistic synthetic patient cohorts (FHIR/CSV) from a schema spec for dev and testing.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
