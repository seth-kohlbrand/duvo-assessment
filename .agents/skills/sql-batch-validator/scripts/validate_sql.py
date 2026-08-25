#!/usr/bin/env python3
"""
PostgreSQL SQL Static Validator
Validates SQL files for common errors before execution.
No database connection required.

Usage:
  python3 validate_sql.py <file.sql>
  python3 validate_sql.py <file.sql> --verbose
  echo "SELECT 1" | python3 validate_sql.py --stdin
"""

import sys
import re
import os
import argparse
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

@dataclass
class Issue:
    severity: Severity
    line: int
    message: str
    suggestion: str = ""
    context: str = ""

@dataclass
class Statement:
    sql: str
    start_line: int
    end_line: int
    statement_type: str = ""  # CREATE TABLE, INSERT, etc.
    object_name: str = ""     # table/index/policy name

@dataclass
class ValidationResult:
    file_path: str
    statements: List[Statement] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    tables_created: List[str] = field(default_factory=list)
    tables_referenced: List[str] = field(default_factory=list)

# ============================================================================
# SQL PARSER — Split into individual statements
# ============================================================================

def split_statements(sql: str) -> List[Statement]:
    """Split a SQL file into individual statements, respecting quotes,
    dollar-quoted strings, and comments."""
    statements = []
    current = []
    line_num = 1
    start_line = 1
    i = 0
    chars = sql
    n = len(chars)

    while i < n:
        c = chars[i]

        # Track line numbers
        if c == '\n':
            line_num += 1

        # Skip single-line comments
        if c == '-' and i + 1 < n and chars[i + 1] == '-':
            while i < n and chars[i] != '\n':
                current.append(chars[i])
                i += 1
            continue

        # Skip block comments
        if c == '/' and i + 1 < n and chars[i + 1] == '*':
            current.append(c)
            i += 1
            current.append(chars[i])
            i += 1
            while i < n:
                if chars[i] == '*' and i + 1 < n and chars[i + 1] == '/':
                    current.append(chars[i])
                    i += 1
                    current.append(chars[i])
                    i += 1
                    break
                if chars[i] == '\n':
                    line_num += 1
                current.append(chars[i])
                i += 1
            continue

        # Handle dollar-quoted strings ($$...$$, $function$...$function$, etc.)
        if c == '$':
            # Find the dollar-quote tag
            tag_match = re.match(r'\$([a-zA-Z_]*)\$', chars[i:])
            if tag_match:
                tag = tag_match.group(0)
                current.append(tag)
                i += len(tag)
                # Find closing tag
                while i < n:
                    if chars[i:i+len(tag)] == tag:
                        current.append(tag)
                        i += len(tag)
                        break
                    if chars[i] == '\n':
                        line_num += 1
                    current.append(chars[i])
                    i += 1
                continue

        # Handle single-quoted strings
        if c == "'":
            current.append(c)
            i += 1
            while i < n:
                if chars[i] == "'" and i + 1 < n and chars[i + 1] == "'":
                    # Escaped quote
                    current.append("''")
                    i += 2
                    continue
                if chars[i] == "'":
                    current.append(chars[i])
                    i += 1
                    break
                if chars[i] == '\n':
                    line_num += 1
                current.append(chars[i])
                i += 1
            continue

        # Statement terminator
        if c == ';':
            current.append(c)
            stmt_text = ''.join(current).strip()
            if stmt_text and stmt_text != ';':
                stmt = Statement(sql=stmt_text, start_line=start_line, end_line=line_num)
                _classify_statement(stmt)
                statements.append(stmt)
            current = []
            start_line = line_num
            i += 1
            continue

        if not current and c in (' ', '\t', '\n'):
            # Skip leading whitespace for new statement
            if c == '\n':
                start_line = line_num
            i += 1
            continue

        current.append(c)
        i += 1

    # Handle last statement without semicolon
    remaining = ''.join(current).strip()
    if remaining and not remaining.startswith('--'):
        stmt = Statement(sql=remaining, start_line=start_line, end_line=line_num)
        _classify_statement(stmt)
        statements.append(stmt)

    return statements

def _classify_statement(stmt: Statement):
    """Identify what type of SQL statement this is and what object it targets."""
    sql = stmt.sql.strip()
    # Remove leading comments
    lines = sql.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('--') and not stripped.startswith('/*'):
            sql = stripped
            break

    sql_upper = sql.upper()

    patterns = [
        (r'CREATE\s+(OR\s+REPLACE\s+)?TABLE\s+(IF\s+NOT\s+EXISTS\s+)?(\S+)', 'CREATE TABLE'),
        (r'CREATE\s+(OR\s+REPLACE\s+)?INDEX\s+(IF\s+NOT\s+EXISTS\s+)?(\S+)', 'CREATE INDEX'),
        (r'CREATE\s+(OR\s+REPLACE\s+)?FUNCTION\s+(\S+)', 'CREATE FUNCTION'),
        (r'CREATE\s+(OR\s+REPLACE\s+)?TRIGGER\s+(\S+)', 'CREATE TRIGGER'),
        (r'CREATE\s+POLICY\s+"?([^"\s]+)"?\s+ON\s+(\S+)', 'CREATE POLICY'),
        (r'CREATE\s+EXTENSION\s+(IF\s+NOT\s+EXISTS\s+)?("?\S+"?)', 'CREATE EXTENSION'),
        (r'ALTER\s+TABLE\s+(\S+)', 'ALTER TABLE'),
        (r'INSERT\s+INTO\s+(\S+)', 'INSERT INTO'),
        (r'DROP\s+TABLE\s+(IF\s+EXISTS\s+)?(\S+)', 'DROP TABLE'),
        (r'SELECT\b', 'SELECT'),
        (r'UPDATE\s+(\S+)', 'UPDATE'),
        (r'DELETE\s+FROM\s+(\S+)', 'DELETE'),
    ]

    for pattern, stmt_type in patterns:
        match = re.search(pattern, sql, re.IGNORECASE)
        if match:
            stmt.statement_type = stmt_type
            # Extract object name from the last capture group
            groups = [g for g in match.groups() if g and g.upper() not in ('OR', 'REPLACE', 'IF', 'NOT', 'EXISTS')]
            if groups:
                stmt.object_name = groups[-1].strip('"').strip("'")
            break

    if not stmt.statement_type:
        stmt.statement_type = sql_upper.split()[0] if sql_upper.split() else 'UNKNOWN'

# ============================================================================
# VALIDATORS
# ============================================================================

def check_balanced_parens(stmt: Statement) -> List[Issue]:
    """Check for mismatched parentheses."""
    issues = []
    depth = 0
    in_string = False
    in_dollar = False
    sql = stmt.sql

    i = 0
    while i < len(sql):
        c = sql[i]
        if c == "'" and not in_dollar:
            in_string = not in_string
        elif c == '$' and not in_string:
            # Simple dollar-quote detection
            if sql[i:i+2] == '$$':
                in_dollar = not in_dollar
                i += 1
        elif not in_string and not in_dollar:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth < 0:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        line=stmt.start_line,
                        message=f"Unmatched closing parenthesis in {stmt.statement_type} {stmt.object_name}",
                        suggestion="Check for missing opening parenthesis"
                    ))
                    return issues
        i += 1

    if depth > 0:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message=f"Unclosed parenthesis ({depth} open) in {stmt.statement_type} {stmt.object_name}",
            suggestion=f"Missing {depth} closing parenthesis/parentheses"
        ))

    return issues

def check_quotes(stmt: Statement) -> List[Issue]:
    """Check for unclosed string literals."""
    issues = []
    single_count = 0
    in_dollar = False

    for i, c in enumerate(stmt.sql):
        if c == '$' and stmt.sql[i:i+2] == '$$':
            in_dollar = not in_dollar
        elif c == "'" and not in_dollar:
            single_count += 1

    if single_count % 2 != 0:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message=f"Unclosed single quote in {stmt.statement_type}",
            suggestion="Check for missing closing quote. Use '' to escape single quotes inside strings."
        ))

    return issues

def check_create_table_guards(stmt: Statement) -> List[Issue]:
    """Note unguarded table creation without assuming idempotency is required."""
    issues = []
    if stmt.statement_type == 'CREATE TABLE':
        if 'IF NOT EXISTS' not in stmt.sql.upper():
            issues.append(Issue(
                severity=Severity.INFO,
                line=stmt.start_line,
                message=f"CREATE TABLE {stmt.object_name} without IF NOT EXISTS",
                suggestion="Confirm this migration runs once. Use IF NOT EXISTS only when an existing definition is acceptable.",
                context=stmt.object_name
            ))
    return issues

def check_drop_guards(stmt: Statement) -> List[Issue]:
    """Warn if DROP TABLE doesn't have IF EXISTS."""
    issues = []
    if stmt.statement_type == 'DROP TABLE':
        if 'IF EXISTS' not in stmt.sql.upper():
            issues.append(Issue(
                severity=Severity.WARNING,
                line=stmt.start_line,
                message=f"DROP TABLE without IF EXISTS",
                suggestion="Add IF EXISTS to prevent error when table doesn't exist."
            ))
    return issues

def check_uuid_format(stmt: Statement) -> List[Issue]:
    """Validate UUID format in INSERT statements."""
    issues = []
    if stmt.statement_type != 'INSERT INTO':
        return issues

    uuid_pattern = r"'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'"
    uuids = re.findall(uuid_pattern, stmt.sql)

    for uuid in uuids:
        # Check for obviously fake/test UUIDs that might collide
        if uuid.startswith('00000000-0000-0000-0000'):
            issues.append(Issue(
                severity=Severity.INFO,
                line=stmt.start_line,
                message=f"Zero-prefix UUID detected: {uuid}",
                suggestion="Fine for demo/seed data. Ensure this doesn't collide with real data."
            ))

    return issues

def check_rls_policy(stmt: Statement) -> List[Issue]:
    """Validate RLS policy syntax and common patterns."""
    issues = []
    if stmt.statement_type != 'CREATE POLICY':
        return issues

    sql_upper = stmt.sql.upper()

    # INSERT policies can use WITH CHECK without USING.
    if 'USING' not in sql_upper and 'WITH CHECK' not in sql_upper:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message="RLS policy has neither USING nor WITH CHECK",
            suggestion="Define row visibility with USING and proposed-row validation with WITH CHECK as appropriate to the command."
        ))

    # Tenant keys vary by schema; flag common omissions for review rather than failure.
    if not any(key in sql_upper for key in ('TENANT_ID', 'ORGANIZATION_ID', 'ORG_ID', 'ACCOUNT_ID')):
        issues.append(Issue(
            severity=Severity.WARNING,
            line=stmt.start_line,
            message="RLS policy does not reference a common tenant key",
            suggestion="Confirm whether the table is global or tenant scope is enforced through a reviewed helper."
        ))

    # Check for auth.jwt() usage
    if 'AUTH.JWT()' not in sql_upper and 'AUTH.UID()' not in sql_upper:
        issues.append(Issue(
            severity=Severity.WARNING,
            line=stmt.start_line,
            message="RLS policy doesn't reference auth.jwt() or auth.uid()",
            suggestion="Supabase RLS should use auth.jwt() -> 'app_metadata' or auth.uid() for scoping."
        ))

    return issues

def check_references_order(statements: List[Statement]) -> List[Issue]:
    """Check that tables are created before they're referenced."""
    issues = []
    created_tables = set()

    for stmt in statements:
        if stmt.statement_type == 'CREATE TABLE':
            table_name = stmt.object_name.lower().strip('"')

            # Check FK references in this CREATE TABLE
            fk_matches = re.findall(r'REFERENCES\s+(\S+)', stmt.sql, re.IGNORECASE)
            for ref_table in fk_matches:
                ref_clean = ref_table.lower().strip('"').split('(')[0]
                if ref_clean not in created_tables and ref_clean != table_name:
                    issues.append(Issue(
                        severity=Severity.INFO,
                        line=stmt.start_line,
                        message=f"Table {stmt.object_name} references {ref_clean}, which is not created earlier in this file",
                        suggestion=f"Confirm {ref_clean} exists in the prior schema or move its creation earlier."
                    ))

            created_tables.add(table_name)

        elif stmt.statement_type == 'INSERT INTO':
            table_name = stmt.object_name.lower().strip('"')
            if table_name not in created_tables:
                # Not necessarily an error — table might exist from a previous migration
                issues.append(Issue(
                    severity=Severity.INFO,
                    line=stmt.start_line,
                    message=f"INSERT INTO {table_name} — table not created in this file",
                    suggestion="Table must exist from a previous migration. Ensure migration order is correct."
                ))

        elif stmt.statement_type in ('CREATE INDEX', 'ALTER TABLE', 'CREATE POLICY'):
            # Extract table name from ON clause
            on_match = re.search(r'\bON\s+(\S+)', stmt.sql, re.IGNORECASE)
            if on_match:
                ref_table = on_match.group(1).lower().strip('"')
                if ref_table not in created_tables:
                    issues.append(Issue(
                        severity=Severity.INFO,
                        line=stmt.start_line,
                        message=f"{stmt.statement_type} references {ref_table} — not created in this file",
                        suggestion="Table must exist from a previous migration."
                    ))

    return issues

def check_common_typos(stmt: Statement) -> List[Issue]:
    """Catch common SQL typos and mistakes."""
    issues = []
    sql = stmt.sql
    sql_upper = sql.upper()

    # TIMESTAMPZ instead of TIMESTAMPTZ
    if 'TIMESTAMPZ ' in sql_upper or 'TIMESTAMPZ)' in sql_upper:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message="Typo: TIMESTAMPZ should be TIMESTAMPTZ",
            suggestion="PostgreSQL type is TIMESTAMPTZ (with T before Z)"
        ))

    # BOOLEN instead of BOOLEAN
    if 'BOOLEN' in sql_upper:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message="Typo: BOOLEN should be BOOLEAN",
            suggestion="Correct spelling is BOOLEAN"
        ))

    # INTERGER instead of INTEGER
    if 'INTERGER' in sql_upper:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message="Typo: INTERGER should be INTEGER",
            suggestion="Correct spelling is INTEGER"
        ))

    # DEAFULT instead of DEFAULT
    if 'DEAFULT' in sql_upper:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message="Typo: DEAFULT should be DEFAULT",
            suggestion="Correct spelling is DEFAULT"
        ))

    # CASCDE instead of CASCADE
    if 'CASCDE' in sql_upper:
        issues.append(Issue(
            severity=Severity.ERROR,
            line=stmt.start_line,
            message="Typo: CASCDE should be CASCADE",
            suggestion="Correct spelling is CASCADE"
        ))

    # CHECK for trailing comma before closing paren in CREATE TABLE
    if stmt.statement_type == 'CREATE TABLE':
        # Find content between outermost parens
        paren_match = re.search(r'\((.*)\)', stmt.sql, re.DOTALL)
        if paren_match:
            inner = paren_match.group(1).rstrip()
            if inner.rstrip().endswith(','):
                issues.append(Issue(
                    severity=Severity.ERROR,
                    line=stmt.end_line,
                    message=f"Trailing comma before closing parenthesis in CREATE TABLE {stmt.object_name}",
                    suggestion="Remove the trailing comma after the last column/constraint definition."
                ))

    # JSONB default should be '{}' or '[]', not {} or []
    if 'JSONB' in sql_upper and stmt.statement_type == 'CREATE TABLE':
        if re.search(r"DEFAULT\s+\{", sql):
            issues.append(Issue(
                severity=Severity.ERROR,
                line=stmt.start_line,
                message="JSONB DEFAULT must be a quoted string: '{}' not {}",
                suggestion="Use DEFAULT '{}'::JSONB or DEFAULT '[]'::JSONB"
            ))

    # NOW() vs CURRENT_TIMESTAMP (both valid, just info)
    # no issue needed

    # Serial vs UUID — just flag SERIAL usage as info
    if 'SERIAL' in sql_upper and stmt.statement_type == 'CREATE TABLE':
        issues.append(Issue(
            severity=Severity.INFO,
            line=stmt.start_line,
            message=f"Using SERIAL in {stmt.object_name}",
            suggestion="Confirm that sequence-backed identifiers match the repository's key strategy."
        ))

    return issues

def check_insert_column_count(stmt: Statement) -> List[Issue]:
    """Check that INSERT column count matches VALUES count."""
    issues = []
    if stmt.statement_type != 'INSERT INTO':
        return issues

    # Extract column list
    col_match = re.search(r'INSERT\s+INTO\s+\S+\s*\(([^)]+)\)', stmt.sql, re.IGNORECASE)
    if not col_match:
        return issues

    columns = [c.strip() for c in col_match.group(1).split(',')]
    num_cols = len(columns)

    # Find all VALUES clauses
    values_section = re.search(r'VALUES\s*(.*)', stmt.sql, re.IGNORECASE | re.DOTALL)
    if not values_section:
        return issues

    # Count value tuples — this is approximate (won't catch nested function calls perfectly)
    # but catches the most common cases
    values_text = values_section.group(1)

    # Split by top-level ),( patterns
    depth = 0
    current_tuple_start = None
    tuples = []

    for i, c in enumerate(values_text):
        if c == '(':
            if depth == 0:
                current_tuple_start = i
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0 and current_tuple_start is not None:
                tuples.append(values_text[current_tuple_start + 1:i])
                current_tuple_start = None

    for idx, val_tuple in enumerate(tuples):
        # Rough count — split by commas not inside quotes or parens
        val_depth = 0
        in_str = False
        comma_count = 0
        for c in val_tuple:
            if c == "'" and not in_str:
                in_str = True
            elif c == "'" and in_str:
                in_str = False
            elif c == '(' and not in_str:
                val_depth += 1
            elif c == ')' and not in_str:
                val_depth -= 1
            elif c == ',' and not in_str and val_depth == 0:
                comma_count += 1

        num_vals = comma_count + 1
        if num_vals != num_cols:
            issues.append(Issue(
                severity=Severity.ERROR,
                line=stmt.start_line,
                message=f"Column count mismatch in INSERT INTO {stmt.object_name}: {num_cols} columns but tuple {idx + 1} has {num_vals} values",
                suggestion=f"Expected {num_cols} values per row. Check for missing or extra commas."
            ))

    return issues

# ============================================================================
# MAIN VALIDATOR
# ============================================================================

def validate_sql(sql: str, file_path: str = "<stdin>") -> ValidationResult:
    """Run all validators against a SQL string."""
    result = ValidationResult(file_path=file_path)

    # Parse statements
    result.statements = split_statements(sql)

    if not result.statements:
        result.issues.append(Issue(
            severity=Severity.WARNING,
            line=1,
            message="No SQL statements found in file",
            suggestion="File may be empty or missing semicolons between statements."
        ))
        return result

    # Track created tables for reference checking
    for stmt in result.statements:
        if stmt.statement_type == 'CREATE TABLE':
            result.tables_created.append(stmt.object_name)

        # Collect referenced tables
        refs = re.findall(r'REFERENCES\s+(\S+)', stmt.sql, re.IGNORECASE)
        for ref in refs:
            ref_clean = ref.split('(')[0].strip('"')
            result.tables_referenced.append(ref_clean)

    # Run per-statement validators
    for stmt in result.statements:
        result.issues.extend(check_balanced_parens(stmt))
        result.issues.extend(check_quotes(stmt))
        result.issues.extend(check_create_table_guards(stmt))
        result.issues.extend(check_drop_guards(stmt))
        result.issues.extend(check_uuid_format(stmt))
        result.issues.extend(check_rls_policy(stmt))
        result.issues.extend(check_common_typos(stmt))
        result.issues.extend(check_insert_column_count(stmt))

    # Run cross-statement validators
    result.issues.extend(check_references_order(result.statements))

    return result

def print_report(result: ValidationResult):
    """Print a human-readable validation report."""
    print(f"\n{'=' * 60}")
    print(f"SQL Static Validation Report")
    print(f"File: {result.file_path}")
    print(f"{'=' * 60}")

    # Statement summary
    print(f"\nStatements found: {len(result.statements)}")
    type_counts = {}
    for stmt in result.statements:
        type_counts[stmt.statement_type] = type_counts.get(stmt.statement_type, 0) + 1
    for stype, count in sorted(type_counts.items()):
        print(f"  {stype}: {count}")

    if result.tables_created:
        print(f"\nTables created: {len(result.tables_created)}")
        for t in result.tables_created:
            print(f"  - {t}")

    # Issues by severity
    errors = [i for i in result.issues if i.severity == Severity.ERROR]
    warnings = [i for i in result.issues if i.severity == Severity.WARNING]
    infos = [i for i in result.issues if i.severity == Severity.INFO]

    if not result.issues:
        print(f"\n✅ No issues found! SQL looks good.")
    else:
        if errors:
            print(f"\n❌ ERRORS ({len(errors)}):")
            print("-" * 40)
            for issue in errors:
                print(f"  Line {issue.line}: {issue.message}")
                if issue.suggestion:
                    print(f"    → {issue.suggestion}")

        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)}):")
            print("-" * 40)
            for issue in warnings:
                print(f"  Line {issue.line}: {issue.message}")
                if issue.suggestion:
                    print(f"    → {issue.suggestion}")

        if infos:
            print(f"\nℹ️  INFO ({len(infos)}):")
            print("-" * 40)
            for issue in infos:
                print(f"  Line {issue.line}: {issue.message}")
                if issue.suggestion:
                    print(f"    → {issue.suggestion}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Summary: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info")
    if errors:
        print(f"⛔ Fix {len(errors)} error(s) before running this SQL")
    elif warnings:
        print(f"⚠️  Review {len(warnings)} warning(s) — may cause issues in some environments")
    else:
        print(f"✅ Ready to run")
    print(f"{'=' * 60}\n")

    return len(errors)

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run focused static checks on a PostgreSQL SQL file.")
    parser.add_argument('file', nargs='?', help="SQL file to inspect")
    parser.add_argument('--stdin', action='store_true', help="Read SQL from standard input")
    parser.add_argument('--verbose', action='store_true', help="Print parsed statement summaries")
    args = parser.parse_args()

    if args.stdin:
        sql = sys.stdin.read()
        file_path = "<stdin>"
    elif args.file:
        file_path = args.file
        if not os.path.isfile(file_path):
            parser.error(f"SQL file not found: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as sql_file:
            sql = sql_file.read()
    else:
        parser.error("provide a SQL file or use --stdin")

    result = validate_sql(sql, file_path)

    if args.verbose:
        print("\nStatements parsed:")
        for i, stmt in enumerate(result.statements):
            truncated = stmt.sql[:80].replace('\n', ' ')
            print(f"  {i+1}. [{stmt.start_line}-{stmt.end_line}] {stmt.statement_type} {stmt.object_name}: {truncated}...")

    error_count = print_report(result)
    sys.exit(1 if error_count > 0 else 0)
