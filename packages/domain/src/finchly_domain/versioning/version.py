"""SemVer schema version handling per ADR-010 §7."""

import re
from functools import total_ordering


@total_ordering
class SchemaVersion:
    """Semantic versioning representation for document schemas (major.minor.patch)."""

    SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

    def __init__(self, version_str: str) -> None:
        """Parse SemVer string into major, minor, patch integers."""
        match = self.SEMVER_PATTERN.match(version_str.strip())
        if not match:
            raise ValueError(
                f"Invalid SemVer schema version '{version_str}'. Expected format: 'X.Y.Z' (e.g. '1.0.0')."
            )
        self.major = int(match.group(1))
        self.minor = int(match.group(2))
        self.patch = int(match.group(3))

    @property
    def version_string(self) -> str:
        """Return formatted SemVer string."""
        return f"{self.major}.{self.minor}.{self.patch}"

    def is_breaking_relative_to(self, target: "SchemaVersion") -> bool:
        """Check if target represents a major breaking change relative to self."""
        return target.major > self.major

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if isinstance(other, str):
            try:
                other = SchemaVersion(other)
            except ValueError:
                return False
        if not isinstance(other, SchemaVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other: object) -> bool:
        """Ordering comparison."""
        if isinstance(other, str):
            other = SchemaVersion(other)
        if not isinstance(other, SchemaVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __hash__(self) -> int:
        """Hash representation."""
        return hash((self.major, self.minor, self.patch))

    def __str__(self) -> str:
        """String representation."""
        return self.version_string

    def __repr__(self) -> str:
        """Developer representation."""
        return f"SchemaVersion('{self.version_string}')"
