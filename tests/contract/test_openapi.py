"""Contract test verifying that committed openapi.json matches generated OpenAPI."""

import json

from finchly_contracts.generator import OPENAPI_SPEC_PATH, generate_openapi_spec


def test_openapi_spec_has_no_drift() -> None:
    """Verify that committed openapi.json matches the live app definition."""
    assert OPENAPI_SPEC_PATH.exists(), f"Committed spec does not exist at {OPENAPI_SPEC_PATH}"

    with open(OPENAPI_SPEC_PATH, encoding="utf-8") as f:
        committed_spec = json.load(f)

    generated_spec = generate_openapi_spec()

    # Compare serializations for exact canonical match
    committed_str = json.dumps(committed_spec, sort_keys=True, indent=2)
    generated_str = json.dumps(generated_spec, sort_keys=True, indent=2)

    assert committed_str == generated_str, (
        "OpenAPI contract drift detected! Run `python -m finchly_contracts.generator` and commit the updated openapi.json."
    )


def test_openapi_contains_required_endpoints() -> None:
    """Verify that essential operational and catalog endpoints exist in OpenAPI."""
    generated_spec = generate_openapi_spec()
    paths = generated_spec.get("paths", {})

    assert "/healthz" in paths, "Missing /healthz route in OpenAPI"
    assert "/readyz" in paths, "Missing /readyz route in OpenAPI"
    assert "/api/v1/info" in paths, "Missing /api/v1/info route in OpenAPI"
    assert "/api/v1/error-catalogue" in paths, "Missing /api/v1/error-catalogue route in OpenAPI"
