#!/usr/bin/env python3
"""Database migration linter enforcing ADR-009 tenancy and RLS policy.

Enforces:
1. Every tenant-owned table must include a `tenant_id` column.
2. Every tenant-owned table must enable and force row-level security (FORCE RLS).
3. Every tenant-owned table must define a tenant isolation policy.
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


def lint_migration_file(file_path: Path) -> list[str]:
    """Inspect an individual migration file for tenancy and RLS compliance."""
    errors: list[str] = []
    content = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        return [f"{file_path.name}: SyntaxError parsing Python AST: {e}"]

    created_tables: dict[str, list[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Detect op.create_table('table_name', ...)
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

    # Extract all string literals assigned in lists/tuples in the file (e.g. TENANT_TABLES)
    grouped_tables: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            for elt in node.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    grouped_tables.add(elt.value)

    # Check for generic looped RLS patterns like `ALTER TABLE {table} ENABLE ROW LEVEL SECURITY`
    generic_enable_rls = bool(
        re.search(
            r"ALTER\s+TABLE\s+\{\w+\}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", content, re.IGNORECASE
        )
    )
    generic_force_rls = bool(
        re.search(
            r"ALTER\s+TABLE\s+\{\w+\}\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", content, re.IGNORECASE
        )
    )
    generic_policy = bool(
        re.search(r"CREATE\s+POLICY\s+\w+\s+ON\s+\{\w+\}", content, re.IGNORECASE)
    )

    for table_name, cols in created_tables.items():
        if table_name in SYSTEM_TABLES:
            continue

        # 1. tenant_id column check
        if "tenant_id" not in cols:
            errors.append(
                f"{file_path.name}: Tenant-owned table '{table_name}' is missing required 'tenant_id' column."
            )

        # 2. ENABLE ROW LEVEL SECURITY check
        enable_rls_regex = rf"ALTER\s+TABLE\s+{table_name}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY"
        has_enable_rls = bool(re.search(enable_rls_regex, content, re.IGNORECASE)) or (
            generic_enable_rls and table_name in grouped_tables
        )
        if not has_enable_rls:
            errors.append(
                f"{file_path.name}: Table '{table_name}' missing 'ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;'."
            )

        # 3. FORCE ROW LEVEL SECURITY check
        force_rls_regex = rf"ALTER\s+TABLE\s+{table_name}\s+FORCE\s+ROW\s+LEVEL\s+SECURITY"
        has_force_rls = bool(re.search(force_rls_regex, content, re.IGNORECASE)) or (
            generic_force_rls and table_name in grouped_tables
        )
        if not has_force_rls:
            errors.append(
                f"{file_path.name}: Table '{table_name}' missing 'ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;'."
            )

        # 4. Policy check
        policy_regex = rf"CREATE\s+POLICY\s+\w+\s+ON\s+{table_name}"
        has_policy = bool(re.search(policy_regex, content, re.IGNORECASE)) or (
            generic_policy and table_name in grouped_tables
        )
        if not has_policy:
            errors.append(
                f"{file_path.name}: Table '{table_name}' missing 'CREATE POLICY ... ON {table_name}' tenant isolation policy."
            )

    return errors


def main() -> int:
    """Run lint checks across all migration files in migrations/versions."""
    if not MIGRATIONS_DIR.exists():
        print(f"Migrations directory not found at {MIGRATIONS_DIR}")
        return 0

    migration_files = sorted(MIGRATIONS_DIR.glob("*.py"))
    if not migration_files:
        print("No migration files found.")
        return 0

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
