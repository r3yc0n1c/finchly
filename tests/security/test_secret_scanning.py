"""Security test verifying secret scanning enforcement.

Enforces AGENTS.md §5, §16, and SEC-015:
No secrets, private keys, real customer documents or personal data are committed.
Acceptance criteria: A planted fake secret fails the secret scan.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_FILE = REPO_ROOT / ".secrets.baseline"


def test_baseline_file_exists() -> None:
    """Verify that .secrets.baseline exists and is initialized."""
    assert BASELINE_FILE.exists(), "Missing .secrets.baseline file"


def test_clean_repo_passes_secret_scan() -> None:
    """Verify that current repository files pass secret scanning."""
    cmd = [
        sys.executable,
        "-m",
        "detect_secrets.main",
        "scan",
        "--baseline",
        str(BASELINE_FILE),
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"Secret scan failed on repository:\n{result.stderr}"


def test_planted_fake_secret_fails_scan() -> None:
    """Verify that planting a fake secret is detected and fails the scan."""
    probe_file = REPO_ROOT / "tests" / "security" / "_probe_fake_secret.py"
    fake_secret = "AKIAIMNOJVGFDXYZ4567"  # pragma: allowlist secret

    try:
        probe_file.write_text(
            f'# Deliberate test probe\nAWS_SECRET_KEY = "{fake_secret}"\n',
            encoding="utf-8",
        )

        import shutil

        hook_bin = shutil.which("detect-secrets-hook")
        if hook_bin:
            cmd = [hook_bin, "--baseline", str(BASELINE_FILE), str(probe_file)]
        else:
            cmd = [
                "uv",
                "run",
                "detect-secrets-hook",
                "--baseline",
                str(BASELINE_FILE),
                str(probe_file),
            ]
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)

        assert result.returncode != 0, (
            f"Secret scanner should have rejected planted secret, got returncode 0.\nStdout: {result.stdout}"
        )
        assert (
            "Potential secrets about to be committed" in result.stdout
            or "Secret Type" in result.stdout
        ), f"Expected secret detection warning in output, got:\n{result.stdout}"
    finally:
        if probe_file.exists():
            probe_file.unlink()
