from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import anyio
from fastmcp import Client
from fastmcp.exceptions import ToolError


def _content_text(error: Exception) -> str:
    return str(error)


async def verify() -> None:
    logging.getLogger("fastmcp").setLevel(logging.CRITICAL)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(__file__).resolve().parents[1]
        server_path = repo_root / "implementation" / "mcp_server.py"
        db_path = Path(tmpdir) / "verify.db"
        config = {
            "mcpServers": {
                "sqlite-lab": {
                    "command": sys.executable,
                    "args": [str(server_path)],
                    "env": {
                        **os.environ,
                        "SQLITE_LAB_DB": str(db_path),
                        "FASTMCP_LOG_LEVEL": "CRITICAL",
                    },
                }
            }
        }

        async with Client(config) as client:
            tools = await client.list_tools()
            tool_names = {tool.name for tool in tools}
            assert tool_names == {"search", "insert", "aggregate"}, tool_names
            print("PASS tools:", ", ".join(sorted(tool_names)))

            resources = await client.list_resources()
            resource_uris = {str(resource.uri) for resource in resources}
            assert "schema://database" in resource_uris, resource_uris
            print("PASS resources:", ", ".join(sorted(resource_uris)))

            templates = await client.list_resource_templates()
            template_uris = {template.uriTemplate for template in templates}
            assert "schema://table/{table_name}" in template_uris, template_uris
            print("PASS resource templates:", ", ".join(sorted(template_uris)))

            schema_text = (await client.read_resource("schema://database"))[0].text
            schema = json.loads(schema_text)
            assert {"students", "courses", "enrollments"} <= set(schema["tables"])
            print("PASS schema://database includes students, courses, enrollments")

            students_schema = json.loads((await client.read_resource("schema://table/students"))[0].text)
            assert students_schema["table"] == "students"
            print("PASS schema://table/students")

            search_result = await client.call_tool(
                "search",
                {
                    "table": "students",
                    "filters": {"cohort": "A1"},
                    "order_by": "score",
                    "descending": True,
                    "limit": 2,
                },
            )
            assert search_result.data["count"] == 2
            print("PASS search students in cohort A1:", search_result.data["rows"])

            insert_result = await client.call_tool(
                "insert",
                {
                    "table": "students",
                    "values": {
                        "name": "Linh Vu",
                        "cohort": "A1",
                        "email": "linh.vu.verify@example.edu",
                        "score": 86.0,
                    },
                },
            )
            assert insert_result.data["row"]["id"]
            print("PASS insert student:", insert_result.data["row"])

            aggregate_result = await client.call_tool(
                "aggregate",
                {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
            )
            assert aggregate_result.data["rows"]
            print("PASS aggregate average score by cohort:", aggregate_result.data["rows"])

            try:
                await client.call_tool("search", {"table": "missing_table"})
            except ToolError as exc:
                assert "unknown table" in _content_text(exc)
                print("PASS invalid table rejected:", _content_text(exc))
            else:
                raise AssertionError("invalid table did not raise ToolError")


def main() -> None:
    anyio.run(verify)


if __name__ == "__main__":
    main()
