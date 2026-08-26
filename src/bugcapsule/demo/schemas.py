"""API schemas for the demonstration order service."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    """Validated order creation payload."""

    product_sku: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    quantity: int = Field(ge=1, le=100)


class OrderRead(BaseModel):
    """Public order representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_sku: str
    quantity: int
    created_at: datetime


class DemoStatus(BaseModel):
    """Observable connection leak state."""

    leaked_sessions: int
    pool_size: int
    max_overflow: int
    state: str
