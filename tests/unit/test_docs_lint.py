"""Unit tests for documentation and tracking artifacts validity."""

import pytest

from scripts.lint_docs import DOCS_DIR, lint_adrs, lint_features_json, lint_progress_md

docs_present = pytest.mark.skipif(
    not DOCS_DIR.exists(),
    reason="docs/ directory not present in checkout (untracked / git-ignored)",
)


@docs_present
def test_features_json_is_valid() -> None:
    """Verify docs/FEATURES.json satisfies schema invariants."""
    errors = lint_features_json()
    assert not errors, f"docs/FEATURES.json lint errors:\n{errors}"


@docs_present
def test_progress_md_is_valid() -> None:
    """Verify docs/PROGRESS.md contains required tracking sections."""
    errors = lint_progress_md()
    assert not errors, f"docs/PROGRESS.md lint errors:\n{errors}"


@docs_present
def test_adrs_render_and_follow_standard() -> None:
    """Verify all ADR markdown files conform to structure requirements."""
    errors = lint_adrs()
    assert not errors, f"docs/adr lint errors:\n{errors}"
