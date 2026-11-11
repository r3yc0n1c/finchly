"""Export JSON Schemas from Pydantic models to schemas/ directory.

Satisfies ADR-010 §10 and FIN-004 acceptance criteria.
"""

import json
from pathlib import Path

from finchly_domain.schemas.canonical import SupplierInvoicePayload
from finchly_domain.schemas.envelope import CanonicalEnvelope
from finchly_domain.schemas.evidence import Evidence
from finchly_domain.schemas.field import Field
from finchly_domain.schemas.primitives import DateValue, Money, Quantity


def export_all_schemas(target_dir: Path | None = None) -> list[Path]:
    """Generate and write formatted JSON Schema files to disk."""
    base_dir = target_dir or Path(__file__).resolve().parents[5] / "schemas"
    canonical_dir = base_dir / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    schemas_to_export = {
        canonical_dir / "envelope.json": CanonicalEnvelope.model_json_schema(),
        canonical_dir / "supplier_invoice.json": SupplierInvoicePayload.model_json_schema(),
        canonical_dir / "money.json": Money.model_json_schema(),
        canonical_dir / "quantity.json": Quantity.model_json_schema(),
        canonical_dir / "date_value.json": DateValue.model_json_schema(),
        canonical_dir / "evidence.json": Evidence.model_json_schema(),
        canonical_dir / "field_str.json": Field[str].model_json_schema(),
    }

    written: list[Path] = []
    for file_path, schema in schemas_to_export.items():
        formatted_json = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        file_path.write_text(formatted_json, encoding="utf-8")
        written.append(file_path)

    return written


def main() -> None:
    """CLI entrypoint for make schema-export."""
    written = export_all_schemas()
    print(f"Exported {len(written)} JSON Schema files to schemas/canonical:")
    for path in written:
        print(f"  - {path.name}")


if __name__ == "__main__":
    main()
