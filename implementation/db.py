from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """Raised when a request cannot be safely executed."""


SUPPORTED_OPERATORS = {
    "=",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "like",
    "in",
    "contains",
    "startswith",
    "endswith",
    "is_null",
}

SUPPORTED_AGGREGATES = {"count", "avg", "sum", "min", "max"}
MAX_LIMIT = 100


class SQLiteAdapter:
    """Small validation-first SQLite adapter for MCP tool calls."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def list_tables(self) -> list[str]:
        sql = """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """
        with self.connect() as conn:
            return [row["name"] for row in conn.execute(sql)]

    def get_table_schema(self, table: str) -> dict[str, Any]:
        self._validate_table(table)
        with self.connect() as conn:
            columns = [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "not_null": bool(row["notnull"]),
                    "default": row["dflt_value"],
                    "primary_key": bool(row["pk"]),
                }
                for row in conn.execute(f"PRAGMA table_info({self._quote_identifier(table)})")
            ]
            foreign_keys = [
                {
                    "column": row["from"],
                    "references_table": row["table"],
                    "references_column": row["to"],
                    "on_update": row["on_update"],
                    "on_delete": row["on_delete"],
                }
                for row in conn.execute(f"PRAGMA foreign_key_list({self._quote_identifier(table)})")
            ]
        return {"table": table, "columns": columns, "foreign_keys": foreign_keys}

    def describe_database(self) -> dict[str, Any]:
        tables = self.list_tables()
        return {
            "database": str(self.db_path),
            "tables": {table: self.get_table_schema(table) for table in tables},
        }

    def search(
        self,
        table: str,
        columns: Any = None,
        filters: Any = None,
        limit: Any = 20,
        offset: Any = 0,
        order_by: Any = None,
        descending: Any = False,
    ) -> dict[str, Any]:
        self._validate_table(table)
        selected_columns = self._validate_columns(table, columns)
        limit = self._validate_limit(limit)
        offset = self._validate_offset(offset)

        select_sql = "*"
        if selected_columns:
            select_sql = ", ".join(self._quote_identifier(column) for column in selected_columns)

        where_sql, params = self._build_where(table, filters)
        sql = f"SELECT {select_sql} FROM {self._quote_identifier(table)}{where_sql}"

        order_by = self._normalize_optional_string(order_by)
        descending = self._normalize_bool(descending)
        if order_by:
            self._validate_column(table, order_by)
            direction = "DESC" if descending else "ASC"
            sql += f" ORDER BY {self._quote_identifier(order_by)} {direction}"

        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params)]

        return {
            "table": table,
            "columns": selected_columns or self._column_names(table),
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "rows": rows,
        }

    def insert(self, table: str, values: Any) -> dict[str, Any]:
        self._validate_table(table)
        values = self._coerce_jsonish(values)
        if not isinstance(values, dict) or not values:
            raise ValidationError("insert values must be a non-empty object")

        for column in values:
            self._validate_column(table, column)

        columns = list(values)
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(self._quote_identifier(column) for column in columns)
        sql = f"INSERT INTO {self._quote_identifier(table)} ({column_sql}) VALUES ({placeholders})"

        with self.connect() as conn:
            try:
                cursor = conn.execute(sql, [values[column] for column in columns])
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValidationError(f"insert failed integrity validation: {exc}") from exc

            inserted = self._fetch_inserted_row(conn, table, values, cursor.lastrowid)

        return {"table": table, "row": inserted}

    def aggregate(
        self,
        table: str,
        metric: str,
        column: Any = None,
        filters: Any = None,
        group_by: Any = None,
    ) -> dict[str, Any]:
        self._validate_table(table)
        metric = metric.lower()
        if metric not in SUPPORTED_AGGREGATES:
            raise ValidationError(
                f"unsupported aggregate metric '{metric}'. "
                f"Supported metrics: {', '.join(sorted(SUPPORTED_AGGREGATES))}"
            )

        column = self._normalize_optional_string(column)
        aggregate_expression = self._aggregate_expression(table, metric, column)
        group_columns = self._normalize_group_by(table, group_by)
        select_parts = [self._quote_identifier(column_name) for column_name in group_columns]
        select_parts.append(f"{aggregate_expression} AS value")

        where_sql, params = self._build_where(table, filters)
        sql = f"SELECT {', '.join(select_parts)} FROM {self._quote_identifier(table)}{where_sql}"

        if group_columns:
            grouped = ", ".join(self._quote_identifier(column_name) for column_name in group_columns)
            sql += f" GROUP BY {grouped} ORDER BY {grouped}"

        with self.connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params)]

        return {
            "table": table,
            "metric": metric,
            "column": column,
            "group_by": group_columns,
            "rows": rows,
        }

    def _fetch_inserted_row(
        self,
        conn: sqlite3.Connection,
        table: str,
        values: dict[str, Any],
        lastrowid: int,
    ) -> dict[str, Any]:
        primary_keys = [
            column["name"]
            for column in self.get_table_schema(table)["columns"]
            if column["primary_key"]
        ]
        if len(primary_keys) == 1:
            pk = primary_keys[0]
            pk_value = values.get(pk, lastrowid)
            row = conn.execute(
                f"SELECT * FROM {self._quote_identifier(table)} WHERE {self._quote_identifier(pk)} = ?",
                [pk_value],
            ).fetchone()
            if row:
                return dict(row)
        return dict(values)

    def _aggregate_expression(self, table: str, metric: str, column: str | None) -> str:
        if metric == "count" and column is None:
            return "COUNT(*)"
        if column is None:
            raise ValidationError(f"aggregate metric '{metric}' requires a column")
        self._validate_column(table, column)
        return f"{metric.upper()}({self._quote_identifier(column)})"

    def _build_where(
        self,
        table: str,
        filters: Any,
    ) -> tuple[str, list[Any]]:
        normalized_filters = self._normalize_filters(filters)
        if not normalized_filters:
            return "", []

        clauses: list[str] = []
        params: list[Any] = []

        for filter_spec in normalized_filters:
            column = filter_spec["column"]
            operator = filter_spec["op"].lower()
            value = filter_spec.get("value")
            self._validate_column(table, column)

            column_sql = self._quote_identifier(column)
            if operator not in SUPPORTED_OPERATORS:
                raise ValidationError(
                    f"unsupported filter operator '{operator}'. "
                    f"Supported operators: {', '.join(sorted(SUPPORTED_OPERATORS))}"
                )

            if operator in {"=", "!=", "<", "<=", ">", ">=", "like"}:
                clauses.append(f"{column_sql} {operator.upper()} ?")
                params.append(value)
            elif operator == "in":
                if not isinstance(value, list) or not value:
                    raise ValidationError("the 'in' operator requires a non-empty list value")
                placeholders = ", ".join("?" for _ in value)
                clauses.append(f"{column_sql} IN ({placeholders})")
                params.extend(value)
            elif operator == "contains":
                clauses.append(f"{column_sql} LIKE ?")
                params.append(f"%{value}%")
            elif operator == "startswith":
                clauses.append(f"{column_sql} LIKE ?")
                params.append(f"{value}%")
            elif operator == "endswith":
                clauses.append(f"{column_sql} LIKE ?")
                params.append(f"%{value}")
            elif operator == "is_null":
                clauses.append(f"{column_sql} IS {'NULL' if bool(value) else 'NOT NULL'}")

        return f" WHERE {' AND '.join(clauses)}", params

    def _normalize_filters(
        self,
        filters: Any,
    ) -> list[dict[str, Any]]:
        filters = self._coerce_jsonish(filters)
        if filters is None:
            return []
        if isinstance(filters, dict):
            return [{"column": column, "op": "=", "value": value} for column, value in filters.items()]
        if not isinstance(filters, list):
            raise ValidationError("filters must be an object or a list of filter objects")

        normalized = []
        for filter_spec in filters:
            if not isinstance(filter_spec, dict):
                raise ValidationError("each filter must be an object")
            column = filter_spec.get("column")
            operator = filter_spec.get("op", filter_spec.get("operator", "="))
            if not isinstance(column, str) or not column:
                raise ValidationError("each filter requires a column")
            if not isinstance(operator, str) or not operator:
                raise ValidationError("each filter requires a string operator")
            normalized.append({"column": column, "op": operator, "value": filter_spec.get("value")})
        return normalized

    def _normalize_group_by(self, table: str, group_by: Any) -> list[str]:
        group_by = self._coerce_jsonish(group_by)
        if group_by is None:
            return []
        if isinstance(group_by, str):
            group_by = self._normalize_optional_string(group_by)
            if group_by is None:
                return []
        group_columns = [group_by] if isinstance(group_by, str) else group_by
        if not isinstance(group_columns, list) or not group_columns:
            raise ValidationError("group_by must be a column name or a non-empty list of column names")
        for column in group_columns:
            if not isinstance(column, str):
                raise ValidationError("group_by entries must be column names")
            self._validate_column(table, column)
        return group_columns

    def _validate_table(self, table: str) -> None:
        if not isinstance(table, str) or table not in self.list_tables():
            raise ValidationError(f"unknown table '{table}'")

    def _validate_columns(self, table: str, columns: Any) -> list[str]:
        columns = self._coerce_jsonish(columns)
        if isinstance(columns, str):
            columns = [column.strip() for column in columns.split(",") if column.strip()]
        if columns is None:
            return []
        if not isinstance(columns, list) or not columns:
            raise ValidationError("columns must be a non-empty list when provided")
        for column in columns:
            if not isinstance(column, str):
                raise ValidationError("columns must contain only column names")
            self._validate_column(table, column)
        return columns

    def _validate_column(self, table: str, column: str) -> None:
        if column not in self._column_names(table):
            raise ValidationError(f"unknown column '{column}' for table '{table}'")

    def _column_names(self, table: str) -> list[str]:
        with self.connect() as conn:
            return [
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({self._quote_identifier(table)})")
            ]

    def _validate_limit(self, limit: Any) -> int:
        if isinstance(limit, str) and limit.strip().isdigit():
            limit = int(limit)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValidationError("limit must be an integer")
        if limit < 1 or limit > MAX_LIMIT:
            raise ValidationError(f"limit must be between 1 and {MAX_LIMIT}")
        return limit

    def _validate_offset(self, offset: Any) -> int:
        if isinstance(offset, str) and offset.strip().isdigit():
            offset = int(offset)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValidationError("offset must be a non-negative integer")
        return offset

    def _coerce_jsonish(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if stripped == "" or stripped.lower() == "null":
            return None
        if stripped[0:1] in {"{", "["}:
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"invalid JSON input: {exc.msg}") from exc
        return value

    def _normalize_optional_string(self, value: Any) -> str | None:
        value = self._coerce_jsonish(value)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValidationError("expected a string value")
        stripped = value.strip()
        return stripped or None

    def _normalize_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off", "", "null"}:
                return False
        raise ValidationError("expected a boolean value")

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'
