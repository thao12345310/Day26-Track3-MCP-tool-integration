from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from implementation.mcp_server import build_server


def test_mcp_tools_resources_and_errors(tmp_path: Path) -> None:
    async def run() -> None:
        mcp = build_server(tmp_path / "lab.db")
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools} == {"search", "insert", "aggregate"}

            resources = await client.list_resources()
            assert "schema://database" in {str(resource.uri) for resource in resources}

            templates = await client.list_resource_templates()
            assert "schema://table/{table_name}" in {
                template.uriTemplate for template in templates
            }

            schema_text = (await client.read_resource("schema://table/students"))[0].text
            assert json.loads(schema_text)["table"] == "students"

            result = await client.call_tool(
                "search",
                {"table": "students", "filters": {"cohort": "A1"}, "limit": 2},
            )
            assert result.data["count"] == 2

            with pytest.raises(ToolError, match="unknown table"):
                await client.call_tool("search", {"table": "missing"})

    anyio.run(run)
