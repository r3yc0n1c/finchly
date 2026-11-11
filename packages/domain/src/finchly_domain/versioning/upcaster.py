"""Upcaster registry for schema evolution per ADR-010 §7.

Policy:
1. Reviewed documents are immutable at their version.
2. When reading a historical version under a newer schema, registered upcasters
   run deterministically on read to produce the target version structure.
3. Breaking changes require an upcaster and a SemVer version bump.
"""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from finchly_domain.versioning.version import SchemaVersion

UpcasterFunc = Callable[[dict[str, Any]], dict[str, Any]]


class UpcasterRegistry:
    """Registry managing version-to-version payload transformations."""

    def __init__(self) -> None:
        """Initialize empty upcaster registry."""
        self._upcasters: dict[tuple[str, str, str], UpcasterFunc] = {}

    def register(
        self,
        document_type: str,
        from_version: str,
        to_version: str,
        func: UpcasterFunc,
    ) -> None:
        """Register a deterministic transformation function from from_version to to_version."""
        v_from = SchemaVersion(from_version)
        v_to = SchemaVersion(to_version)
        if v_to <= v_from:
            raise ValueError(
                f"Target version '{to_version}' must be strictly greater than source version '{from_version}'."
            )
        key = (document_type, v_from.version_string, v_to.version_string)
        self._upcasters[key] = func

    def find_path(
        self, document_type: str, from_version: str, to_version: str
    ) -> list[tuple[str, str, UpcasterFunc]]:
        """Find sequential path of upcaster transitions using breadth-first search."""
        v_from = SchemaVersion(from_version).version_string
        v_to = SchemaVersion(to_version).version_string

        if v_from == v_to:
            return []

        # Build adjacency graph for this document_type
        graph: dict[str, list[tuple[str, UpcasterFunc]]] = {}
        for (doc_type, src, dst), func in self._upcasters.items():
            if doc_type == document_type:
                graph.setdefault(src, []).append((dst, func))

        # BFS queue: (current_version, path_so_far)
        queue: list[tuple[str, list[tuple[str, str, UpcasterFunc]]]] = [(v_from, [])]
        visited = {v_from}

        while queue:
            curr, path = queue.pop(0)
            if curr == v_to:
                return path

            for nxt, func in graph.get(curr, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [(curr, nxt, func)]))

        return []

    def upcast(
        self,
        document_type: str,
        payload: dict[str, Any],
        from_version: str,
        to_version: str,
    ) -> dict[str, Any]:
        """Apply sequential upcasters to transform payload from from_version to to_version."""
        v_from = SchemaVersion(from_version)
        v_to = SchemaVersion(to_version)

        if v_from == v_to:
            return deepcopy(payload)

        if v_to < v_from:
            raise ValueError(
                f"Cannot downcast payload from version '{from_version}' to older version '{to_version}'."
            )

        path = self.find_path(document_type, from_version, to_version)
        if not path:
            raise ValueError(
                f"No registered upcaster path found for document_type '{document_type}' "
                f"from version '{from_version}' to '{to_version}'."
            )

        current_data = deepcopy(payload)
        for _step_from, _step_to, func in path:
            current_data = func(current_data)

        return current_data


# Global default registry instance
default_upcaster_registry = UpcasterRegistry()
