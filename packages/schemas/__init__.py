"""Shared Pydantic schemas for API responses."""

from packages.schemas.common import DeclaredValue, ProvenanceRef
from packages.schemas.people import PaginatedPeople, PersonDetail, PersonSummary

__all__ = [
    "DeclaredValue",
    "PaginatedPeople",
    "PersonDetail",
    "PersonSummary",
    "ProvenanceRef",
]
