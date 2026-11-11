"""Field envelope model conforming to ADR-010 §3 and AI-009.

Every business field in Finchly is wrapped in a Field[T] to guarantee that:
1. Absent components are marked as 'missing', never fabricated or defaulted to zero.
2. Raw text is preserved alongside the normalized value.
3. Traceable evidence records and normalizer versions are explicitly retained.
"""

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydanticField

from finchly_domain.schemas.evidence import Evidence
from finchly_domain.schemas.primitives import FieldStatus


class Field[T](BaseModel):
    """Generic wrapper for business document fields."""

    model_config = ConfigDict(frozen=True)

    raw: str | None = PydanticField(
        default=None,
        description="Raw text snippet extracted from source document prior to normalization.",
    )
    value: T | None = PydanticField(
        default=None,
        description="Normalized typed value, or None if missing or unparseable.",
    )
    status: FieldStatus = PydanticField(
        ...,
        description="Explicit lifecycle status: present, missing, ambiguous, derived, or unsupported.",
    )
    normalizer_version: str | None = PydanticField(
        default=None,
        description="Version string of the deterministic normalizer that computed value.",
    )
    evidence: list[Evidence] = PydanticField(
        default_factory=list,
        description="One or more evidence records linking this field to source blocks.",
    )

    @model_validator(mode="after")
    def validate_status_and_value(self) -> "Field[T]":
        """Enforce AI-009 status and value consistency invariants."""
        if self.status == FieldStatus.MISSING and self.value is not None:
            raise ValueError(
                f"Field with status 'missing' must have value=None, but observed value: {self.value}"
            )
        if self.status in (FieldStatus.PRESENT, FieldStatus.DERIVED) and self.value is None:
            raise ValueError(f"Field with status '{self.status.value}' requires a non-None value.")
        return self

    @classmethod
    def missing(cls, raw: str | None = None) -> "Field[T]":
        """Factory for an explicitly absent field."""
        return cls(raw=raw, value=None, status=FieldStatus.MISSING)

    @classmethod
    def present(
        cls,
        value: T,
        raw: str | None = None,
        normalizer_version: str | None = None,
        evidence: list[Evidence] | None = None,
    ) -> "Field[T]":
        """Factory for a present, normalized field."""
        return cls(
            raw=raw,
            value=value,
            status=FieldStatus.PRESENT,
            normalizer_version=normalizer_version,
            evidence=evidence or [],
        )

    @classmethod
    def derived(
        cls,
        value: T,
        raw: str | None = None,
        normalizer_version: str | None = None,
        evidence: list[Evidence] | None = None,
    ) -> "Field[T]":
        """Factory for a deterministically calculated or derived field."""
        return cls(
            raw=raw,
            value=value,
            status=FieldStatus.DERIVED,
            normalizer_version=normalizer_version,
            evidence=evidence or [],
        )
