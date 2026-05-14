from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).with_name("lab.db")

SCHEMA_SQL = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;

CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cohort TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    score REAL NOT NULL CHECK (score >= 0 AND score <= 100)
);

CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits > 0)
);

CREATE TABLE enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    grade REAL NOT NULL CHECK (grade >= 0 AND grade <= 100),
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE (student_id, course_id)
);
"""

SEED_SQL = """
INSERT INTO students (name, cohort, email, score) VALUES
    ('An Nguyen', 'A1', 'an.nguyen@example.edu', 91.5),
    ('Binh Tran', 'A1', 'binh.tran@example.edu', 84.0),
    ('Chi Le', 'A2', 'chi.le@example.edu', 88.5),
    ('Dung Pham', 'A2', 'dung.pham@example.edu', 76.0),
    ('Mai Hoang', 'B1', 'mai.hoang@example.edu', 94.0);

INSERT INTO courses (code, title, credits) VALUES
    ('MCP101', 'Model Context Protocol Fundamentals', 3),
    ('DB201', 'Applied Database Systems', 4),
    ('AI310', 'AI Tool Integration Studio', 3);

INSERT INTO enrollments (student_id, course_id, grade, status) VALUES
    (1, 1, 95.0, 'active'),
    (1, 2, 89.0, 'active'),
    (2, 1, 82.5, 'active'),
    (3, 1, 87.0, 'active'),
    (3, 3, 90.0, 'active'),
    (4, 2, 73.5, 'completed'),
    (5, 3, 96.0, 'active');
"""


def create_database(db_path: str | Path = DEFAULT_DB_PATH, reset: bool = False) -> Path:
    """Create the lab SQLite database and seed data."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if reset and path.exists():
        path.unlink()

    should_initialize = reset or not path.exists()
    if should_initialize:
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA_SQL)
            conn.executescript(SEED_SQL)
            conn.commit()

    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset the SQLite lab database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to the SQLite database file.")
    parser.add_argument("--reset", action="store_true", help="Recreate the database from scratch.")
    args = parser.parse_args()

    path = create_database(args.db, reset=args.reset)
    print(f"Database ready: {path}")


if __name__ == "__main__":
    main()
