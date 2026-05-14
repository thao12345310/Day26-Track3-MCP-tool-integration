# SQLite FastMCP Lab Server

This project implements the Day 26 Track 3 lab: a FastMCP server backed by SQLite. It exposes three MCP tools (`search`, `insert`, `aggregate`) plus schema resources for the whole database and individual tables.

## Project Structure

```text
implementation/
  db.py                  # SQLite adapter, validation, safe SQL construction
  init_db.py             # reproducible schema and seed data
  mcp_server.py          # FastMCP tools and resources
  verify_server.py       # repeatable MCP smoke test
  start_inspector.sh     # MCP Inspector helper
  tests/
    test_db.py
    test_mcp_server.py
client_configs/
  claude_mcp.example.json
  codex_config.example.toml
  gemini_settings.example.json
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python implementation/init_db.py --reset
```

The database is created at `implementation/lab.db`. The MCP server also creates it automatically if it is missing.

## Run the Server

Most MCP clients use stdio:

```bash
.venv/bin/python implementation/mcp_server.py
```

The process waits for MCP JSON-RPC messages on stdin/stdout, so it is normal for this command to look idle when started directly in a terminal.

Optional HTTP/SSE transports are available for demos:

```bash
.venv/bin/python implementation/mcp_server.py --transport http --host 127.0.0.1 --port 8000
.venv/bin/python implementation/mcp_server.py --transport sse --host 127.0.0.1 --port 8000
```

## Tools

### `search`

Search rows in a known table with filters, selected columns, ordering, and pagination.

Example arguments:

```json
{
  "table": "students",
  "filters": { "cohort": "A1" },
  "columns": ["name", "email", "score"],
  "order_by": "score",
  "descending": true,
  "limit": 5,
  "offset": 0
}
```

Filters can be simple equality objects or a list of filter objects:

```json
[
  { "column": "score", "op": ">=", "value": 85 },
  { "column": "cohort", "op": "in", "value": ["A1", "A2"] }
]
```

Supported operators: `=`, `!=`, `<`, `<=`, `>`, `>=`, `like`, `in`, `contains`, `startswith`, `endswith`, `is_null`.

### `insert`

Insert one row into a known table.

```json
{
  "table": "students",
  "values": {
    "name": "Linh Vu",
    "cohort": "A1",
    "email": "linh.vu@example.edu",
    "score": 86
  }
}
```

### `aggregate`

Run `count`, `avg`, `sum`, `min`, or `max`, optionally with filters and grouping.

```json
{
  "table": "students",
  "metric": "avg",
  "column": "score",
  "group_by": "cohort"
}
```

`count` may omit `column`; all other aggregate metrics require one.

## Resources

- `schema://database`: full database schema as JSON
- `schema://table/{table_name}`: schema for one table, for example `schema://table/students`

## Verification

Run the automated smoke test:

```bash
.venv/bin/python implementation/verify_server.py
```

Run the pytest suite:

```bash
.venv/bin/python -m pytest
```

The smoke test verifies:

- starting the MCP server as a subprocess over stdio
- tool discovery for `search`, `insert`, and `aggregate`
- resource discovery for `schema://database`
- resource template discovery for `schema://table/{table_name}`
- valid `search`, `insert`, and `aggregate` calls
- invalid table rejection with a clear error

## MCP Inspector

```bash
implementation/start_inspector.sh
```

In Inspector, confirm that:

- the three tools appear with input schemas
- `schema://database` appears as a resource
- `schema://table/{table_name}` appears as a resource template
- a valid search succeeds
- `{"table": "missing_table"}` passed to `search` returns an error

## Client Configuration

Use absolute paths. To get this repo path:

```bash
pwd
```

### Claude Code

Copy `client_configs/claude_mcp.example.json` into the appropriate Claude MCP config location and replace `/ABSOLUTE/PATH/TO/REPO`.

### Codex

Add this shape to `~/.codex/config.toml`, replacing the path:

```toml
[mcp_servers.sqlite_lab]
command = "/ABSOLUTE/PATH/TO/REPO/.venv/bin/python"
args = ["/ABSOLUTE/PATH/TO/REPO/implementation/mcp_server.py"]
```

### Gemini CLI

```bash
gemini mcp add sqlite-lab /ABSOLUTE/PATH/TO/REPO/.venv/bin/python /ABSOLUTE/PATH/TO/REPO/implementation/mcp_server.py --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list
```

Then try:

```bash
gemini --allowed-mcp-server-names sqlite-lab --yolo -p "Use the sqlite-lab MCP server to show the top 2 students by score and read schema://table/students."
```

## Demo Checklist

For a short demo video, show:

1. `implementation/verify_server.py` passing.
2. Inspector or a real MCP client discovering `search`, `insert`, `aggregate`.
3. Reading `schema://database` and `schema://table/students`.
4. Searching students in cohort `A1`.
5. Inserting a new student.
6. Aggregating average score by cohort.
7. An invalid call, such as searching `missing_table`, returning a clear error.
