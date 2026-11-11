"""Unit tests for database migration linter per ADR-009 and FIN-007."""

from pathlib import Path

from scripts.migration_lint import lint_migration_file


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
