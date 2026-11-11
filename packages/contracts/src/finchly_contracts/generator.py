"""OpenAPI schema generation utilities for Finchly."""

import json
from pathlib import Path
from typing import Any

from finchly_api.main import app

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent
OPENAPI_SPEC_PATH = CONTRACTS_DIR / "openapi.json"


def generate_openapi_spec() -> dict[str, Any]:
    """Generate OpenAPI specification dictionary from FastAPI app."""
    return app.openapi()


def dump_openapi_spec(target_path: Path = OPENAPI_SPEC_PATH) -> None:
    """Generate and write formatted OpenAPI spec to file."""
    spec = generate_openapi_spec()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    dump_openapi_spec()
    print(f"OpenAPI specification written to {OPENAPI_SPEC_PATH}")
