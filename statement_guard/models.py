"""Pydantic models for the normalized statement and validation output."""
from __future__ import annotations

from datetime import date as Date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Status(str, Enum):
    READY = "READY"                      # every check passed, nothing auto-changed
    READY_AUTOFIXED = "READY_AUTOFIXED"  # passed after evidence-backed auto-repairs (listed)
    READY_REVIEWED = "READY_REVIEWED"    # a human edited it and re-validation passed
    NEEDS_REVIEW = "NEEDS_REVIEW"        # inconsistent or unverifiable: do NOT import
    UNSUPPORTED = "UNSUPPORTED"          # image-only, encrypted, oversized or not a statement


IMPORTABLE = {Status.READY, Status.READY_AUTOFIXED, Status.READY_REVIEWED}


class Repair(BaseModel):
    kind: str            # direction_swap | ocr_confusable | implied_amount | orphan_line
    row_idx: int | None
    field: str
    before: str
    after: str
    evidence: str


class Txn(BaseModel):
    idx: int
    page: int
    date: Date | None = None
    date_text: str = ""
    value_date: Date | None = None
    description: str = ""
    ref: str | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    balance: Decimal | None = None
    source_text: str = ""                       # original text of the row's lines
    bbox: tuple[float, float, float, float] | None = None
    raw: dict[str, str] = Field(default_factory=dict)  # raw numeric tokens as printed
    notes: list[str] = Field(default_factory=list)     # parser-level uncertainty notes

    @property
    def signed(self) -> Decimal | None:
        if self.debit is None and self.credit is None:
            return None
        return (self.credit or Decimal(0)) - (self.debit or Decimal(0))


class Flag(BaseModel):
    code: str
    severity: str        # error | warn | info
    message: str
    row_idx: int | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class Statement(BaseModel):
    source_name: str = ""
    page_count: int = 0
    opening: Decimal | None = None
    closing: Decimal | None = None
    declared_total_debits: Decimal | None = None
    declared_total_credits: Decimal | None = None
    txns: list[Txn] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    repairs: list[Repair] = Field(default_factory=list)
    reviewer_edits: list[str] = Field(default_factory=list)
    status: Status = Status.NEEDS_REVIEW
    verification_level: str = "none"   # full_chain | totals_only | none
    layout_notes: list[str] = Field(default_factory=list)
    mode: str = ""
    runtime_ms: float = 0.0

    @property
    def importable(self) -> bool:
        return self.status in IMPORTABLE

    def errors(self) -> list[Flag]:
        return [f for f in self.flags if f.severity == "error"]
