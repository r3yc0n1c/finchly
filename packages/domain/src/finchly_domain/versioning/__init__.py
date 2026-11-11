"""Schema versioning and upcaster framework conforming to ADR-010 §7."""

from finchly_domain.versioning.upcaster import (
    UpcasterFunc,
    UpcasterRegistry,
    default_upcaster_registry,
)
from finchly_domain.versioning.version import SchemaVersion

__all__ = [
    "SchemaVersion",
    "UpcasterFunc",
    "UpcasterRegistry",
    "default_upcaster_registry",
]
