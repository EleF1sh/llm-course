from __future__ import annotations

import math
import time
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from pet_hospital_mcp.errors import AdapterError, ErrorEnvelope, validation_error
from pet_hospital_mcp.logging_config import setup_logging
from pet_hospital_mcp.rest_client import PetHospitalClient

logger = setup_logging()

VALID_SPECIES = ("犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他")
VALID_STATUS = ("待就诊", "就诊中", "住院中", "已康复", "慢性病随访")
VALID_SORT_BY = (
    "id",
    "name",
    "ownerName",
    "species",
    "doctor",
    "disease",
    "status",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
)
VALID_ORDER = ("asc", "desc")

Species = Literal["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"]
Status = Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"]
SortBy = Literal[
    "id",
    "name",
    "ownerName",
    "species",
    "doctor",
    "disease",
    "status",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
]
Order = Literal["asc", "desc"]

LIST_PETS_DESCRIPTION = """List pet hospital records via GET /api/v1/pets.

Use this tool when an agent needs to search, filter, sort, or paginate pets
from the existing Go Pet Hospital REST API. Supported query parameters match
the backend exactly: q, name, ownerName, ownerPhone, species, doctor, disease,
status, min, max, sortBy, order, page, pageSize.

Returns the Go API success `data` object: items, total, page, pageSize,
totalPages, totalCost. On failure returns a structured error envelope with
code/message/details.
"""


def _reject_non_finite(value: float | None) -> float | None:
    if value is None:
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")
    if math.isnan(value) or math.isinf(value):
        raise ValueError("NaN and Infinity are not allowed")
    return float(value)


class MedicalRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    visitDate: str | None = None
    doctor: str | None = None
    diagnosis: str | None = None
    symptoms: str | None = None
    treatment: str | None = None
    prescription: list[str] | None = None
    weightKg: float | None = None
    temperature: float | None = None
    followUp: str | None = None
    charge: float | None = None
    createdAt: str | None = None


class ChargeItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    item: str | None = None
    category: str | None = None
    amount: float | None = None
    doctor: str | None = None
    date: str | None = None
    note: str | None = None


class PetItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    species: str
    breed: str | None = None
    gender: str | None = None
    ageMonths: int | None = None
    color: str | None = None
    chipNo: str | None = None
    ownerName: str
    ownerPhone: str
    ownerAddr: str | None = None
    doctor: str | None = None
    disease: str | None = None
    status: str | None = None
    allergy: str | None = None
    note: str | None = None
    # Go may encode empty slices as null.
    records: list[MedicalRecord] | None = None
    charges: list[ChargeItem] | None = None
    totalCost: float | None = None
    visitCount: int | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class ListPetsInput(BaseModel):
    """Strict input model aligned with GET /api/v1/pets query parameters."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = None
    name: str | None = None
    ownerName: str | None = None
    ownerPhone: str | None = None
    species: Species | None = None
    doctor: str | None = None
    disease: str | None = None
    status: Status | None = None
    min: float | None = None
    max: float | None = None
    sortBy: SortBy | None = None
    order: Order | None = None
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=500)

    @field_validator("min", "max", mode="before")
    @classmethod
    def _finite_costs(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("must be a number")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("must be a number") from exc
        return _reject_non_finite(number)

    @field_validator("page", "pageSize", mode="before")
    @classmethod
    def _finite_ints(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("must be an integer")
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError("NaN and Infinity are not allowed")
        return value

    @model_validator(mode="after")
    def _min_le_max(self) -> ListPetsInput:
        if self.min is not None and self.min < 0:
            raise ValueError("min must be >= 0")
        if self.max is not None and self.max < 0:
            raise ValueError("max must be >= 0")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must be <= max")
        return self

    def to_query_params(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        return data


class ListPetsOutput(BaseModel):
    """Success payload corresponding to Go API response.data."""

    model_config = ConfigDict(extra="forbid")

    items: list[PetItem]
    total: int
    page: int
    pageSize: int
    totalPages: int
    totalCost: float


def parse_list_pets_input(raw: dict[str, Any] | None) -> ListPetsInput:
    try:
        return ListPetsInput.model_validate(raw or {})
    except ValidationError as exc:
        raise validation_error(
            "Invalid list_pets arguments",
            details={"errors": exc.errors(include_url=False)},
        ) from exc


def parse_list_pets_output(data: dict[str, Any]) -> ListPetsOutput:
    try:
        return ListPetsOutput.model_validate(data)
    except ValidationError as exc:
        raise AdapterError(
            "BACKEND_INVALID_RESPONSE",
            "Pet Hospital API data does not match the expected list schema",
            details={"errors": exc.errors(include_url=False)},
        ) from exc


async def run_list_pets(
    client: PetHospitalClient,
    raw_args: dict[str, Any] | None,
) -> ListPetsOutput | ErrorEnvelope:
    """Execute list_pets and return either success data or a structured error."""
    started = time.perf_counter()
    status = "error"
    params_for_log: dict[str, Any] = raw_args or {}
    try:
        params = parse_list_pets_input(raw_args)
        params_for_log = params.model_dump(exclude_none=True)
        data = await client.list_pets(params.to_query_params())
        result = parse_list_pets_output(data)
        status = "ok"
        return result
    except AdapterError as exc:
        status = exc.code
        return exc.to_envelope()
    except Exception:
        status = "INTERNAL_ERROR"
        logger.exception(
            "unexpected list_pets failure",
            extra={
                "tool_name": "list_pets",
                "params": params_for_log,
                "status": status,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        return AdapterError(
            "INTERNAL_ERROR",
            "Unexpected internal error while listing pets",
        ).to_envelope()
    finally:
        logger.info(
            "list_pets finished",
            extra={
                "tool_name": "list_pets",
                "params": params_for_log,
                "status": status,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
