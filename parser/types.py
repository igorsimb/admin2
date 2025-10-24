"""Pydantic models for data validation and serialization in the parser app."""

from pydantic import BaseModel


class OfferRow(BaseModel):
    """Represents a single offer row parsed from a supplier website."""

    b: str | None  # brand
    a: str  # article
    price: float | None
    quantity: int | None
    delivery: int | None  # deadline_days
    provider: str | None  # supplier
    rating: float | None
    name: str | None
    is_analog: bool
