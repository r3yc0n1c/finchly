#!/usr/bin/env python3
"""Database migration linter enforcing ADR-009 tenancy and RLS policy.

Enforces:
1. Every tenant-owned table must include a `tenant_id` column.
2. Every tenant-owned table must enable and force row-level security (FORCE RLS).
3. Every tenant-owned table must define a tenant isolation policy referencing `tenant_id`.
"""

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations" / "versions"

# Tables explicitly exempt from tenant_id because they represent global/system identity
SYSTEM_TABLES = {
    "tenants",
    "users",
    "login_attempts",
    "alembic_version",
}


def _extract_string_literals(node: ast.AST) -> set[str]:
    """Extract set of string literals from a List, Tuple, or Set AST node."""
    strings: set[str] = set()
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                strings.add(elt.value)
    return strings


def lint_migration_file(file_path: Path) -> list[str]:
    """Inspect an individual migration file for tenancy and RLS compliance."""
    errors: list[str] = []
    content = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        return [f"{file_path.name}: SyntaxError parsing Python AST: {e}"]

    # 1. Map all top-level variable assignments for resolving loop iterables
    assigned_collections: dict[str, set[str]] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    assigned_collections[target.id] = _extract_string_literals(stmt.value)

    # 2. Extract created tables and their column names
    created_tables: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        is_create_table = (
            isinstance(func, ast.Attribute)
            and func.attr == "create_table"
            and isinstance(func.value, ast.Name)
            and func.value.id == "op"
        )
        if not is_create_table or not node.args:
            continue

        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            table_name = first_arg.value
        else:
            continue

        columns: list[str] = []
        for arg in node.args[1:]:
            if isinstance(arg, ast.Call):
                call_func = arg.func
                is_sa_col = (
                    isinstance(call_func, ast.Attribute)
                    and call_func.attr == "Column"
                    and isinstance(call_func.value, ast.Name)
                    and call_func.value.id == "sa"
                )
                if is_sa_col and arg.args:
                    col_arg = arg.args[0]
                    if isinstance(col_arg, ast.Constant) and isinstance(col_arg.value, str):
                        columns.append(col_arg.value)

        created_tables[table_name] = columns

    # 3. Detect loop-based RLS enforcement that covers specific collections
    loop_covered_tables: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.For) or not isinstance(node.target, ast.Name):
            continue

        var_name = node.target.id
        # Resolve target tables for this loop
        loop_tables: set[str] = set()
        if isinstance(node.iter, ast.Name) and node.iter.id in assigned_collections:
            loop_tables = assigned_collections[node.iter.id]
        elif isinstance(node.iter, (ast.List, ast.Tuple, ast.Set)):
            loop_tables = _extract_string_literals(node.iter)

        if not loop_tables:
            continue

        # Check loop body AST / raw code for generic patterns using var_name
        loop_segment = ast.get_source_segment(content, node) or ""
        v = re.escape(var_name)

        has_loop_enable = bool(
            re.search(rf"\bALTER\s+TABLE\s+\{{{v}\}}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", loop_segment, re.IGNORECASE)
        )
        has_loop_force = bool(
            re.search(rf"\bALTER\s+TABLE\s+\{{{v}\}}\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", loop_segment, re.IGNORECASE)
        )
        has_loop_policy = bool(
            re.search(
                rf"\bCREATE\s+POLICY\s+\w+\s+ON\s+\{{{v}\}}\s+[^;]*\bUSING\s*\([^;]*\btenant_id\b",
                loop_segment,
                re.IGNORECASE,
            )
        )

        if has_loop_enable and has_loop_force and has_loop_policy:
            loop_covered_tables.update(loop_tables)

    # 4. Check each created table
    for table_name, cols in created_tables.items():
        if table_name in SYSTEM_TABLES:
            continue

        # 4a. tenant_id column check
        if "tenant_id" not in cols:
            errors.append(
                f"{file_path.name}: Tenant-owned table '{table_name}' is missing required 'tenant_id' column."
            )

        # 4b. If covered by valid loop, table is verified
        is_loop_covered = table_name in loop_covered_tables

        # 4c. Check literal statements
        esc = re.escape(table_name)
        enable_rls_regex = rf"\bALTER\s+TABLE\s+{esc}\b\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY"
        has_enable_rls = is_loop_covered or bool(re.search(enable_rls_regex, content, re.IGNORECASE))
        if not has_enable_rls:
            errors.append(
                f"{file_path.name}: Table '{table_name}' missing 'ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;'."
            )

        force_rls_regex = rf"\bALTER\s+TABLE\s+{esc}\b\s+FORCE\s+ROW\s+LEVEL\s+SECURITY"
        has_force_rls = is_loop_covered or bool(re.search(force_rls_regex, content, re.IGNORECASE))
        if not has_force_rls:
            errors.append(
                f"{file_path.name}: Table '{table_name}' missing 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;'."
            )

        policy_regex = (
            rf"\bCREATE\s+POLICY\s+\w+\s+ON\s+{esc}\b\s+[^;]*\bUSING\s*\([^;]*\btenant_id\b"
        )
        has_policy = is_loop_covered or bool(re.search(policy_regex, content, re.IGNORECASE))
        if not has_policy:
            errors.append(
                f"{file_path.name}: Table '{table_name}' missing 'CREATE POLICY ... ON {table_name} ... USING (...tenant_id...)' tenant isolation policy."
            )

    return errors


def main() -> int:
    """Run lint checks across all migration files in migrations/versions."""
    if not MIGRATIONS_DIR.exists():
        print(f"[ERROR] Migrations directory not found at {MIGRATIONS_DIR}")
        return 1

    migration_files = sorted(MIGRATIONS_DIR.glob("*.py"))
    if not migration_files:
        print("[ERROR] No migration files found in migrations directory.")
        return 1

    all_errors: list[str] = []
    print(
        f"Linting {len(migration_files)} migration files for ADR-009 tenancy and RLS compliance..."
    )

    for mig_path in migration_files:
        errs = lint_migration_file(mig_path)
        all_errors.extend(errs)

    if all_errors:
        print("\n[ERROR] Migration lint failed:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("[OK] All migrations passed tenancy and RLS lint checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
