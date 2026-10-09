"""Pydantic models mirroring the Go REST API payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MedicalRecord(BaseModel):
    """`records[]` entry of a pet. Optional because the Go API uses omitempty."""

    model_config = ConfigDict(extra="allow")

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


class Charge(BaseModel):
    """`charges[]` entry of a pet."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    item: str | None = None
    category: str | None = None
    amount: float | None = None
    doctor: str | None = None
    date: str | None = None


class Pet(BaseModel):
    """One pet archive inside `items`. `records`/`charges` may be null or arrays."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    species: str | None = None
    breed: str | None = None
    gender: str | None = None
    ageMonths: int | None = None
    color: str | None = None
    chipNo: str | None = None
    ownerName: str | None = None
    ownerPhone: str | None = None
    ownerAddr: str | None = None
    doctor: str | None = None
    disease: str | None = None
    status: str | None = None
    allergy: str | None = None
    note: str | None = None
    records: list[MedicalRecord] | None = None
    charges: list[Charge] | None = None
    totalCost: float | None = None
    visitCount: int | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class ListPetsSuccess(BaseModel):
    """`data` of a successful `GET /api/v1/pets` response."""

    model_config = ConfigDict(extra="forbid")

    items: list[Pet] = Field(description="当前页的宠物档案")
    total: int = Field(description="匹配条件的记录总数")
    page: int = Field(description="当前页码")
    pageSize: int = Field(description="每页条数")
    totalPages: int = Field(description="总页数")
    totalCost: float = Field(description="匹配条件的费用合计")
