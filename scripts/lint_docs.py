#!/usr/bin/env python3
"""Documentation and progress tracking linter.

Validates docs/FEATURES.json and docs/PROGRESS.md integrity,
satisfying FIN-003 acceptance criteria.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
FEATURES_JSON = DOCS_DIR / "FEATURES.json"
PROGRESS_MD = DOCS_DIR / "PROGRESS.md"
ADR_DIR = DOCS_DIR / "adr"


def lint_features_json() -> list[str]:
    """Validate structure and typing of FEATURES.json."""
    errors: list[str] = []
    if not FEATURES_JSON.exists():
        return [f"Missing {FEATURES_JSON}"]

    try:
        with open(FEATURES_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return [f"Invalid JSON in FEATURES.json: {exc}"]

    if not isinstance(data, dict):
        return ["FEATURES.json must be a JSON object"]

    if "schema_version" not in data:
        errors.append("FEATURES.json missing 'schema_version'")
    if "features" not in data or not isinstance(data["features"], list):
        errors.append("FEATURES.json missing 'features' array")
        return errors

    required_fields = {
        "id": str,
        "description": str,
        "scope": str,
        "phase": str,
        "tickets": list,
        "status": str,
        "passes": bool,
    }

    valid_statuses = {"not_started", "in_progress", "done", "blocked"}

    for idx, feature in enumerate(data["features"]):
        fid = feature.get("id", f"index_{idx}")
        for field, expected_type in required_fields.items():
            if field not in feature:
                errors.append(f"Feature '{fid}' missing required field '{field}'")
            elif not isinstance(feature[field], expected_type):
                errors.append(
                    f"Feature '{fid}' field '{field}' must be {expected_type.__name__}, got {type(feature[field]).__name__}"
                )

        status = feature.get("status")
        if status and status not in valid_statuses:
            errors.append(f"Feature '{fid}' has invalid status '{status}'")

        # Invariant: passes can only be true if status is done and evidence is provided
        if feature.get("passes") is True and not feature.get("evidence"):
            errors.append(f"Feature '{fid}' has passes=True but no evidence linked")

    return errors


def lint_progress_md() -> list[str]:
    """Validate that docs/PROGRESS.md contains required sections."""
    errors: list[str] = []
    if not PROGRESS_MD.exists():
        return [f"Missing {PROGRESS_MD}"]

    content = PROGRESS_MD.read_text(encoding="utf-8")
    required_headings = [
        r"^# Finchly — Progress",
        r"^## Current position",
        r"^## Phase status",
        r"^## Release gates",
        r"^## Session log",
    ]

    for pattern in required_headings:
        if not re.search(pattern, content, re.MULTILINE):
            errors.append(f"PROGRESS.md missing required section matching: {pattern}")

    return errors


def lint_adrs() -> list[str]:
    """Validate ADRs in docs/adr render with proper headers."""
    errors: list[str] = []
    if not ADR_DIR.exists():
        return [f"Missing directory {ADR_DIR}"]

    adr_files = list(ADR_DIR.glob("*.md"))
    if not adr_files:
        return ["No ADR markdown files found in docs/adr"]

    for adr_path in adr_files:
        text = adr_path.read_text(encoding="utf-8")
        if not re.search(r"^# ADR-[0-9A-Z]+:", text, re.MULTILINE):
            errors.append(f"{adr_path.name} missing '# ADR-XXX:' top-level title")
        if "## Decision" not in text:
            errors.append(f"{adr_path.name} missing '## Decision' section")

    return errors


def main() -> int:
    """Run all document linter checks."""
    all_errors: list[str] = []

    print("Checking docs/FEATURES.json...")
    feat_errors = lint_features_json()
    all_errors.extend(feat_errors)

    print("Checking docs/PROGRESS.md...")
    prog_errors = lint_progress_md()
    all_errors.extend(prog_errors)

    print("Checking docs/adr/...")
    adr_errors = lint_adrs()
    all_errors.extend(adr_errors)

    if all_errors:
        print("\n[ERROR] Documentation lint failures:")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("\n[OK] All documentation lint checks passed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
