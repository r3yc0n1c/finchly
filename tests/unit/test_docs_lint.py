"""Unit tests for documentation and tracking artifacts validity."""

import json
from pathlib import Path

import pytest

from scripts.lint_docs import (
    DOCS_DIR,
    lint_adrs,
    lint_features_json,
    lint_progress_md,
)

docs_present = pytest.mark.skipif(
    not DOCS_DIR.exists(),
    reason="docs/ directory not present in checkout (untracked / git-ignored)",
)


@docs_present
def test_features_json_is_valid() -> None:
    """Verify repository docs/FEATURES.json satisfies schema invariants."""
    errors = lint_features_json()
    assert not errors, f"docs/FEATURES.json lint errors:\n{errors}"


@docs_present
def test_progress_md_is_valid() -> None:
    """Verify repository docs/PROGRESS.md contains required tracking sections."""
    errors = lint_progress_md()
    assert not errors, f"docs/PROGRESS.md lint errors:\n{errors}"


@docs_present
def test_adrs_render_and_follow_standard() -> None:
    """Verify repository docs/adr markdown files conform to structure requirements."""
    errors = lint_adrs()
    assert not errors, f"docs/adr lint errors:\n{errors}"


def test_features_json_validator_with_fixtures(tmp_path: Path) -> None:
    """Verify features validator logic on valid and invalid synthetic fixtures."""
    # Valid fixture
    valid_file = tmp_path / "FEATURES.json"
    valid_data = {
        "schema_version": "1.0.0",
        "features": [
            {
                "id": "TEST-001",
                "description": "Test feature",
                "scope": "core",
                "phase": "D0",
                "tickets": ["FIN-001"],
                "status": "not_started",
                "passes": False,
            }
        ],
    }
    valid_file.write_text(json.dumps(valid_data), encoding="utf-8")
    assert lint_features_json(valid_file) == []

    # Invalid fixture: missing required schema_version and missing tickets
    invalid_file = tmp_path / "INVALID_FEATURES.json"
    invalid_data = {
        "features": [
            {
                "id": "TEST-002",
                "description": "Missing fields",
                "scope": "core",
                "phase": "D0",
                "status": "not_started",
                "passes": False,
            }
        ]
    }
    invalid_file.write_text(json.dumps(invalid_data), encoding="utf-8")
    errors = lint_features_json(invalid_file)
    assert any("missing 'schema_version'" in e for e in errors)
    assert any("missing required field 'tickets'" in e for e in errors)


def test_progress_md_validator_with_fixtures(tmp_path: Path) -> None:
    """Verify progress markdown validator logic on valid and invalid fixtures."""
    valid_md = tmp_path / "PROGRESS.md"
    valid_md.write_text(
        "# Finchly — Progress\n\n"
        "## Current position\n\n"
        "## Phase status\n\n"
        "## Release gates\n\n"
        "## Session log\n",
        encoding="utf-8",
    )
    assert lint_progress_md(valid_md) == []

    invalid_md = tmp_path / "INVALID_PROGRESS.md"
    invalid_md.write_text("# Finchly\n\nIncomplete\n", encoding="utf-8")
    errors = lint_progress_md(invalid_md)
    assert len(errors) > 0


def test_adrs_validator_with_fixtures(tmp_path: Path) -> None:
    """Verify ADR validator logic on valid and invalid fixtures."""
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()

    valid_adr = adr_dir / "ADR-001.md"
    valid_adr.write_text(
        "# ADR-001: Test Decision\n\n## Status\nApproved\n\n## Decision\nUse PostgreSQL.\n",
        encoding="utf-8",
    )
    assert lint_adrs(adr_dir) == []

    invalid_adr = adr_dir / "ADR-002.md"
    invalid_adr.write_text("# Invalid format without decision\n", encoding="utf-8")
    errors = lint_adrs(adr_dir)
    assert any("missing '## Decision' section" in e for e in errors)
