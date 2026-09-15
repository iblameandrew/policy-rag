"""Role → classification mapping. Fail closed: unknown role is public.

Retrieval must pass the returned `where` clause into Chroma. Python
post-filters are a tripwire, not the authorization layer.
"""

from __future__ import annotations

from typing import Final

ROLES: Final[frozenset[str]] = frozenset({"public", "employee", "hr", "admin"})
CLASSIFICATIONS: Final[frozenset[str]] = frozenset({"public", "internal", "restricted"})

# Who may read each classification.
CLASSIFICATION_ALLOWED_ROLES: Final[dict[str, tuple[str, ...]]] = {
    "public": ("public", "employee", "hr", "admin"),
    "internal": ("employee", "hr", "admin"),
    "restricted": ("hr", "admin"),
}

# Inverse: which classifications a role may retrieve.
ROLE_ALLOWED_CLASSIFICATIONS: Final[dict[str, tuple[str, ...]]] = {
    "public": ("public",),
    "employee": ("public", "internal"),
    "hr": ("public", "internal", "restricted"),
    "admin": ("public", "internal", "restricted"),
}


def normalize_role(role: str | None) -> str:
    """Unknown / missing role → public (fail closed)."""
    if role is None:
        return "public"
    cleaned = role.strip().lower()
    if cleaned in ROLES:
        return cleaned
    return "public"


def allowed_classifications(role: str | None) -> tuple[str, ...]:
    return ROLE_ALLOWED_CLASSIFICATIONS[normalize_role(role)]


def allowed_roles_for_classification(classification: str) -> tuple[str, ...]:
    if classification not in CLASSIFICATION_ALLOWED_ROLES:
        raise ValueError(f"unknown classification: {classification}")
    return CLASSIFICATION_ALLOWED_ROLES[classification]


def chroma_where(role: str | None) -> dict[str, object]:
    """Chroma `where` pre-filter. Restricted is omitted for employee/public."""
    allowed = list(allowed_classifications(role))
    return {"classification": {"$in": allowed}}
