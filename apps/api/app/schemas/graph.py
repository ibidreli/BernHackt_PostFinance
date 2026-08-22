from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

GraphMode = Literal["absolute", "delta"]
GraphFlow = Literal["expense", "income", "both"]
DeltaDirection = Literal["favourable", "unfavourable", "neutral"]
NodeType = Literal["root", "flow", "category", "merchant", "merchant_group", "transaction"]


class GraphDelta(BaseModel):
    baseline_median_chf: float
    diff_chf: float
    diff_pct: float | None
    direction: DeltaDirection


class GraphSummary(BaseModel):
    child_count: int
    transaction_count: int
    total_amount_chf: float
    avg_amount_chf: float


class TransactionPayload(BaseModel):
    id: str
    date: date
    value_date: date
    merchant: str
    merchant_canonical: str
    original_description: str
    amount_chf: float
    flow: Literal["expense", "income"]
    category_main: str | None
    category_sub: str | None
    original_amount: float | None
    original_currency: str | None
    status: str | None


class GraphNode(BaseModel):
    id: str
    label: str
    level: int
    node_type: NodeType
    flow: Literal["expense", "income"] | None = None
    amount_chf: float
    transaction_count: int
    rank: int | None = None
    merchant_count: int | None = None
    category_main: str | None = None
    category_sub: str | None = None
    merchant: str | None = None
    children: list["GraphNode"] | None
    transaction: TransactionPayload | None = None
    delta: GraphDelta | None = None
    summary: GraphSummary | None = None


class GraphResponse(BaseModel):
    month: str
    mode: GraphMode
    flow: GraphFlow
    baseline_months: list[str]
    baseline_label: str | None
    root: GraphNode


class GraphMonthsResponse(BaseModel):
    months: list[str]
    default: str | None
