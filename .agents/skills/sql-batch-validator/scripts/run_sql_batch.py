#!/usr/bin/env python3
"""Validate and execute a SQL file through a direct PostgreSQL connection."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from validate_sql import Severity, Statement, validate_sql


class Status(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StatementResult:
    number: int
    line: int
    statement_type: str
    object_name: str
    status: Status
    duration_ms: float = 0
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and execute PostgreSQL statements from a SQL file."
    )
    parser.add_argument("file", type=Path, help="SQL file to validate and execute")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection string; defaults to DATABASE_URL",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without connecting")
    parser.add_argument(
        "--transaction",
        action="store_true",
        help="Commit only if every statement succeeds; stops at the first SQL error",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop non-transactional execution after the first SQL error",
    )
    parser.add_argument("--verbose", action="store_true", help="Print each statement")
    parser.add_argument("--output-json", type=Path, help="Write a JSON result file")
    return parser.parse_args()


def skipped_result(number: int, statement: Statement) -> StatementResult:
    return StatementResult(
        number=number,
        line=statement.start_line,
        statement_type=statement.statement_type,
        object_name=statement.object_name,
        status=Status.SKIPPED,
    )


def execute(
    statements: list[Statement], database_url: str, *, transaction: bool,
    stop_on_error: bool, verbose: bool
) -> tuple[list[StatementResult], bool]:
    try:
        import psycopg2
    except ImportError as error:
        raise RuntimeError("Install psycopg2-binary to execute SQL") from error

    connection = psycopg2.connect(database_url)
    connection.autocommit = not transaction
    results: list[StatementResult] = []
    rolled_back = False

    try:
        with connection.cursor() as cursor:
            for index, statement in enumerate(statements, start=1):
                if verbose:
                    preview = " ".join(statement.sql.split())[:140]
                    print(f"[{index}/{len(statements)}] line {statement.start_line}: {preview}")

                started = time.perf_counter()
                try:
                    cursor.execute(statement.sql)
                    result = StatementResult(
                        number=index,
                        line=statement.start_line,
                        statement_type=statement.statement_type,
                        object_name=statement.object_name,
                        status=Status.SUCCEEDED,
                        duration_ms=(time.perf_counter() - started) * 1000,
                    )
                except psycopg2.Error as error:
                    result = StatementResult(
                        number=index,
                        line=statement.start_line,
                        statement_type=statement.statement_type,
                        object_name=statement.object_name,
                        status=Status.FAILED,
                        duration_ms=(time.perf_counter() - started) * 1000,
                        error=str(error).strip(),
                    )
                    results.append(result)

                    must_stop = transaction or stop_on_error
                    if must_stop:
                        for pending_index, pending in enumerate(
                            statements[index:], start=index + 1
                        ):
                            results.append(skipped_result(pending_index, pending))
                        break

                    continue

                results.append(result)

        if transaction:
            if any(result.status == Status.FAILED for result in results):
                connection.rollback()
                rolled_back = True
            else:
                connection.commit()
    finally:
        connection.close()

    return results, rolled_back


def write_json(
    path: Path, source: Path, results: list[StatementResult], rolled_back: bool
) -> None:
    payload = {
        "file": str(source),
        "rolled_back": rolled_back,
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.file.is_file():
        print(f"error: SQL file not found: {args.file}", file=sys.stderr)
        return 2

    sql = args.file.read_text(encoding="utf-8")
    validation = validate_sql(sql, str(args.file))
    errors = [issue for issue in validation.issues if issue.severity == Severity.ERROR]
    warnings = [issue for issue in validation.issues if issue.severity == Severity.WARNING]

    for issue in validation.issues:
        print(f"{issue.severity.value.lower()}: line {issue.line}: {issue.message}")

    print(
        f"validation: {len(validation.statements)} statements, "
        f"{len(errors)} errors, {len(warnings)} warnings"
    )

    if errors:
        print("execution skipped because static validation reported errors", file=sys.stderr)
        return 1

    if args.dry_run:
        return 0

    if not args.database_url:
        print("error: provide --database-url or set DATABASE_URL", file=sys.stderr)
        return 2

    try:
        results, rolled_back = execute(
            validation.statements,
            args.database_url,
            transaction=args.transaction,
            stop_on_error=args.stop_on_error,
            verbose=args.verbose,
        )
    except Exception as error:
        print(f"error: database execution failed: {error}", file=sys.stderr)
        return 1

    counts = {status: 0 for status in Status}
    for result in results:
        counts[result.status] += 1
        if result.status == Status.FAILED:
            print(f"failed: statement {result.number}, line {result.line}: {result.error}")

    print(
        "execution: "
        f"{counts[Status.SUCCEEDED]} succeeded, "
        f"{counts[Status.FAILED]} failed, "
        f"{counts[Status.SKIPPED]} skipped, "
        f"rolled_back={str(rolled_back).lower()}"
    )

    if args.output_json:
        write_json(args.output_json, args.file, results, rolled_back)

    return 1 if counts[Status.FAILED] else 0


if __name__ == "__main__":
    raise SystemExit(main())
