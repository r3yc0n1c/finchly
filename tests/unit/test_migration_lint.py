"""Unit tests for database migration linter per ADR-009 and FIN-007."""

from pathlib import Path
from unittest.mock import patch

from scripts.migration_lint import lint_migration_file, main


def test_valid_migration_passes(tmp_path: Path) -> None:
    """Verify that a compliant migration file passes all checks."""
    valid_migration = tmp_path / "0001_valid.py"
    valid_migration.write_text(
        """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
    )
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY;")
    op.execute("CREATE POLICY tenant_isolation_policy ON documents FOR ALL USING (tenant_id = current_setting('app.tenant_id')::uuid);")
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(valid_migration)
    assert errors == []


def test_missing_tenant_id_fails(tmp_path: Path) -> None:
    """Verify that a tenant-owned table missing tenant_id column fails the lint (FIN-007)."""
    invalid_migration = tmp_path / "0002_missing_tenant_id.py"
    invalid_migration.write_text(
        """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
    )
    op.execute("ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE invoices FORCE ROW LEVEL SECURITY;")
    op.execute("CREATE POLICY tenant_isolation_policy ON invoices FOR ALL USING (tenant_id = current_setting('app.tenant_id')::uuid);")
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(invalid_migration)
    assert any("missing required 'tenant_id' column" in err for err in errors)


def test_missing_force_rls_fails(tmp_path: Path) -> None:
    """Verify that a table missing FORCE ROW LEVEL SECURITY fails the lint."""
    invalid_migration = tmp_path / "0003_missing_force_rls.py"
    invalid_migration.write_text(
        """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
    )
    op.execute("ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;")
    op.execute("CREATE POLICY tenant_isolation_policy ON invoices FOR ALL USING (tenant_id = current_setting('app.tenant_id')::uuid);")
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(invalid_migration)
    assert any("FORCE ROW LEVEL SECURITY" in err for err in errors)


def test_system_tables_exempt(tmp_path: Path) -> None:
    """Verify that system tables like users and tenants are exempt from tenant_id check."""
    system_migration = tmp_path / "0004_system.py"
    system_migration.write_text(
        """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
    )
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(system_migration)
    assert errors == []


def test_loop_based_migration_passes(tmp_path: Path) -> None:
    """Verify that a valid loop-based migration over a defined list passes."""
    loop_migration = tmp_path / "0005_loop_valid.py"
    loop_migration.write_text(
        """
from alembic import op
import sqlalchemy as sa

TENANT_TABLES = ["documents", "invoices"]

def upgrade():
    op.create_table("documents", sa.Column("tenant_id", sa.String()))
    op.create_table("invoices", sa.Column("tenant_id", sa.String()))
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")
        op.execute(f"CREATE POLICY p ON {t} FOR ALL USING (tenant_id = current_setting('app.tenant_id')::uuid);")
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(loop_migration)
    assert errors == []


def test_loop_based_migration_omitted_table_fails(tmp_path: Path) -> None:
    """Verify that a table omitted from the looped list fails RLS check."""
    omitted_migration = tmp_path / "0006_loop_omitted.py"
    omitted_migration.write_text(
        """
from alembic import op
import sqlalchemy as sa

TENANT_TABLES = ["documents"]

def upgrade():
    op.create_table("documents", sa.Column("tenant_id", sa.String()))
    op.create_table("invoices", sa.Column("tenant_id", sa.String()))
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")
        op.execute(f"CREATE POLICY p ON {t} FOR ALL USING (tenant_id = current_setting('app.tenant_id')::uuid);")
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(omitted_migration)
    assert any(
        "Table 'invoices' missing 'ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;'" in err
        for err in errors
    )


def test_missing_create_policy_fails(tmp_path: Path) -> None:
    """Verify that a table missing CREATE POLICY fails."""
    policy_missing = tmp_path / "0007_missing_policy.py"
    policy_missing.write_text(
        """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table("documents", sa.Column("tenant_id", sa.String()))
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY;")
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(policy_missing)
    assert any("tenant isolation policy" in err for err in errors)


def test_prefix_collision_detected(tmp_path: Path) -> None:
    """Verify that 'documents' does not falsely satisfy 'documents_archive'."""
    prefix_migration = tmp_path / "0008_prefix.py"
    prefix_migration.write_text(
        """
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table("documents_archive", sa.Column("tenant_id", sa.String()))
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY;")
    op.execute("CREATE POLICY p ON documents FOR ALL USING (tenant_id = current_setting('app.tenant_id')::uuid);")
""",
        encoding="utf-8",
    )
    errors = lint_migration_file(prefix_migration)
    assert any(
        "Table 'documents_archive' missing 'ALTER TABLE documents_archive ENABLE ROW LEVEL SECURITY;'"
        in err
        for err in errors
    )


def test_main_missing_dir_returns_1(tmp_path: Path) -> None:
    """Verify that main() returns exit code 1 when MIGRATIONS_DIR is missing or empty."""
    with patch("scripts.migration_lint.MIGRATIONS_DIR", tmp_path / "nonexistent"):
        assert main() == 1

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with patch("scripts.migration_lint.MIGRATIONS_DIR", empty_dir):
        assert main() == 1
