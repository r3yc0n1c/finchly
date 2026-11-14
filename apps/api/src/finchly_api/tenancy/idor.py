"""IDOR route inspection and tenant scoping verification per ADR-009 §6 and SEC-003."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from finchly_api.auth.dependencies import get_current_auth
from finchly_api.tenancy.connection import get_tenant_db

# Explicitly exempt public endpoints (health checks, metadata, login)
PUBLIC_EXEMPT_ROUTES: set[tuple[str, str]] = {
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("GET", "/api/v1/info"),
    ("GET", "/api/v1/error-catalogue"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/api/v1/openapi.json"),
}


def _dependency_tree_contains(
    dependency: Any, target_callables: tuple[Callable[..., Any], ...]
) -> bool:
    """Recursively check whether a dependency or sub-dependency targets tenant auth."""
    if not dependency:
        return False

    call = getattr(dependency, "call", None)
    if call in target_callables:
        return True

    for sub in getattr(dependency, "dependencies", []):
        if _dependency_tree_contains(sub, target_callables):
            return True

    return False


def find_unscoped_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Scan all registered routes in a FastAPI application and find any missing tenant authentication.

    A route is considered tenant-scoped if it depends on `get_current_auth`, `get_tenant_db`,
    or a composite dependency containing them.
    """
    unscoped: list[tuple[str, str]] = []
    target_auth_deps = (get_current_auth, get_tenant_db)

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        methods = route.methods or {"GET"}
        for method in methods:
            if (method, route.path) in PUBLIC_EXEMPT_ROUTES:
                continue

            # Check route dependencies
            route_has_auth = False

            # 1. Check direct endpoint signature dependencies
            if hasattr(route, "dependant") and route.dependant:
                for endpoint_dep in route.dependant.dependencies:
                    if _dependency_tree_contains(endpoint_dep, target_auth_deps):
                        route_has_auth = True
                        break

            # 2. Check route-level dependencies (from APIRouter / include_router)
            if not route_has_auth and hasattr(route, "dependencies"):
                for route_dep in getattr(route, "dependencies", []):
                    if _dependency_tree_contains(route_dep, target_auth_deps):
                        route_has_auth = True
                        break

            if not route_has_auth:
                unscoped.append((method, route.path))

    return unscoped


def verify_routes_are_tenant_scoped(app: FastAPI) -> None:
    """Assert that every non-public endpoint in the application enforces tenant scoping.

    Raises:
        AssertionError: If one or more routes lack tenant scoping.
    """
    unscoped = find_unscoped_routes(app)
    if unscoped:
        formatted = "\n".join(f"  - {m} {p}" for m, p in unscoped)
        raise AssertionError(
            f"Tenant scoping violation! The following routes lack tenant authentication dependencies:\n{formatted}"
        )
