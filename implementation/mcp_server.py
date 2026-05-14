from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

try:
    from .db import SQLiteAdapter
    from .init_db import DEFAULT_DB_PATH, create_database
except ImportError:  # Allows `python implementation/mcp_server.py`.
    from db import SQLiteAdapter
    from init_db import DEFAULT_DB_PATH, create_database


def build_server(db_path: str | Path | None = None) -> FastMCP:
    database_path = create_database(db_path or os.environ.get("SQLITE_LAB_DB", DEFAULT_DB_PATH))
    adapter = SQLiteAdapter(database_path)
    mcp = FastMCP("SQLite Lab MCP Server")

    @mcp.tool(
        name="search",
        description=(
            "Search rows in a known table with validated columns, filters, ordering, "
            "limit, and offset."
        ),
    )
    def search(
        table: str,
        filters: Any = None,
        columns: Any = None,
        limit: Any = 20,
        offset: Any = 0,
        order_by: Any = None,
        descending: Any = False,
    ) -> dict[str, Any]:
        return adapter.search(
            table=table,
            columns=columns,
            filters=filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )

    @mcp.tool(
        name="insert",
        description="Insert one row into a known table using validated columns and bound values.",
    )
    def insert(table: str, values: Any) -> dict[str, Any]:
        return adapter.insert(table=table, values=values)

    @mcp.tool(
        name="aggregate",
        description=(
            "Run count, avg, sum, min, or max over a known table, with optional filters "
            "and group_by columns."
        ),
    )
    def aggregate(
        table: str,
        metric: str,
        column: Any = None,
        filters: Any = None,
        group_by: Any = None,
    ) -> dict[str, Any]:
        return adapter.aggregate(
            table=table,
            metric=metric,
            column=column,
            filters=filters,
            group_by=group_by,
        )

    @mcp.resource(
        "schema://database",
        name="database_schema",
        mime_type="application/json",
        description="Full schema snapshot for the SQLite lab database.",
    )
    def database_schema() -> str:
        return json.dumps(adapter.describe_database(), indent=2)

    @mcp.resource(
        "schema://table/{table_name}",
        name="table_schema",
        mime_type="application/json",
        description="Schema snapshot for one table in the SQLite lab database.",
    )
    def table_schema(table_name: str) -> str:
        return json.dumps(adapter.get_table_schema(table_name), indent=2)

    return mcp


mcp = build_server()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SQLite lab MCP server.")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http", "sse"],
        help="MCP transport to use. Local clients usually use stdio.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP or SSE transports.")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP or SSE transports.")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port, show_banner=False)


if __name__ == "__main__":
    main()
