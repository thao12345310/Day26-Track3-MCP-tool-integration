from __future__ import annotations

from pathlib import Path

import pytest

from implementation.db import SQLiteAdapter, ValidationError
from implementation.init_db import create_database


@pytest.fixture()
def adapter(tmp_path: Path) -> SQLiteAdapter:
    db_path = create_database(tmp_path / "lab.db", reset=True)
    return SQLiteAdapter(db_path)


def test_search_filters_ordering_and_pagination(adapter: SQLiteAdapter) -> None:
    result = adapter.search(
        "students",
        filters={"cohort": "A1"},
        columns=["name", "score"],
        order_by="score",
        descending=True,
        limit=1,
    )

    assert result["count"] == 1
    assert result["rows"][0] == {"name": "An Nguyen", "score": 91.5}


def test_insert_returns_inserted_row(adapter: SQLiteAdapter) -> None:
    result = adapter.insert(
        "students",
        {
            "name": "Khoa Do",
            "cohort": "B1",
            "email": "khoa.do@example.edu",
            "score": 82.0,
        },
    )

    assert result["row"]["id"] > 0
    assert result["row"]["name"] == "Khoa Do"


def test_aggregate_average_score_by_cohort(adapter: SQLiteAdapter) -> None:
    result = adapter.aggregate("students", "avg", column="score", group_by="cohort")

    rows = {row["cohort"]: row["value"] for row in result["rows"]}
    assert rows["A1"] == pytest.approx(87.75)
    assert rows["A2"] == pytest.approx(82.25)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda db: db.search("missing"), "unknown table"),
        (lambda db: db.search("students", columns=["password"]), "unknown column"),
        (
            lambda db: db.search(
                "students", filters=[{"column": "cohort", "op": "regex", "value": "A.*"}]
            ),
            "unsupported filter operator",
        ),
        (lambda db: db.insert("students", {}), "non-empty object"),
        (lambda db: db.aggregate("students", "median", column="score"), "unsupported aggregate"),
        (lambda db: db.aggregate("students", "avg"), "requires a column"),
    ],
)
def test_validation_errors(adapter: SQLiteAdapter, call, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        call(adapter)
