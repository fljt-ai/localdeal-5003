"""Typed request contracts for the FastAPI transport (business rules stay in services)."""
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class RequestBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class LoginBody(RequestBody):
    email: StrictStr
    password: StrictStr


class RegisterBody(LoginBody):
    name: StrictStr


class ProfileBody(RequestBody):
    name: StrictStr


class FavoriteBody(RequestBody):
    storeId: StrictStr


class ReviewBody(RequestBody):
    rating: StrictInt = Field(ge=1, le=5)
    comment: StrictStr


class PurchaseBody(RequestBody):
    couponId: StrictStr
    idempotencyKey: StrictStr


class RedeemBody(RequestBody):
    code: StrictStr
    storeId: StrictStr


class StockBody(RequestBody):
    stock: StrictInt = Field(ge=0, le=100000)
    expectedStock: StrictInt = Field(ge=0, le=100000)
