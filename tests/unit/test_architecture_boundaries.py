"""Architecture boundary tests.

Enforces AGENTS.md §4 and NFR-006:
The domain package must not import web frameworks, ORMs, queues, or SDKs.
Acceptance criteria: A deliberate domain -> FastAPI import fails import-linter.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
IMPORT_LINTER_CMD = [
    sys.executable,
    "-c",
    "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())",
]


def test_import_linter_passes_on_current_codebase() -> None:
    """Verify that current codebase satisfies all import-linter contracts."""
    result = subprocess.run(
        IMPORT_LINTER_CMD,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"import-linter failed unexpectedly:\n{result.stdout}\n{result.stderr}"
    )
    assert "Contracts: 1 kept, 0 broken." in result.stdout


def test_deliberate_forbidden_import_fails_import_linter() -> None:
    """Verify that a deliberate domain -> FastAPI import is rejected by import-linter."""
    errors_module_file = REPO_ROOT / "packages" / "domain" / "src" / "finchly_domain" / "errors.py"
    original_code = errors_module_file.read_text(encoding="utf-8")
    try:
        # Deliberately inject forbidden import into finchly_domain
        errors_module_file.write_text(
            original_code + "\nimport fastapi  # type: ignore[import-untyped]\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            IMPORT_LINTER_CMD,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, "import-linter should have failed on forbidden import"
        assert "BROKEN" in result.stdout, (
            f"Expected 'BROKEN' in output, got:\n{result.stdout}\n{result.stderr}"
        )
        assert "finchly_domain is not allowed to import fastapi" in result.stdout
    finally:
        errors_module_file.write_text(original_code, encoding="utf-8")
