"""Graph aggregation service for the category explorer."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from types import SimpleNamespace

from app.models.transaction import Transaction
from app.schemas.graph import (
    GraphDelta,
    GraphFlow,
    GraphMode,
    GraphNode,
    GraphResponse,
    GraphSummary,
    TransactionPayload,
)

_DELTA_MONTHS = 3
_TOP_MERCHANTS_PER_CATEGORY = 5


@dataclass
class _MerchantBucket:
    amount_chf: float = 0.0
    transactions: list[Transaction] | None = None

    def __post_init__(self):
        if self.transactions is None:
            self.transactions = []


def parse_month(month: str) -> tuple[int, int]:
    try:
        year_s, month_s = month.split("-", 1)
        year = int(year_s)
        mon = int(month_s)
    except (ValueError, TypeError) as exc:
        raise ValueError("month must be YYYY-MM") from exc
    if mon < 1 or mon > 12:
        raise ValueError("month must be YYYY-MM")
    return year, mon


def available_months(transactions: list[Transaction], limit: int = 12) -> list[str]:
    keys = sorted({(t.date.year, t.date.month) for t in transactions if not t.is_transfer})
    months = [f"{year:04d}-{month:02d}" for year, month in keys]
    if limit <= 0:
        return months
    return months[-limit:]


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _prev_months(year: int, month: int, count: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = year, month
    for _ in range(count):
        m -= 1
        if m == 0:
            y -= 1
            m = 12
        months.append((y, m))
    months.reverse()
    return months


def _category_label(main: str | None, sub: str | None) -> str:
    if main and sub:
        return f"{main} // {sub}"
    if main:
        return main
    return "Sonstiges"


def _is_refund_income(t: Transaction) -> bool:
    if t.flow != "income":
        return False
    sub = (t.category_sub or "").lower()
    main = (t.category_main or "").lower()
    return "rückerstattung" in sub or "ruckerstattung" in sub or "rückerstattung" in main


def _build_month_buckets(
    transactions: list[Transaction], year: int, month: int
) -> dict[tuple[str, str, str, str], _MerchantBucket]:
    expense_by_key: dict[tuple[str, str, str], _MerchantBucket] = defaultdict(_MerchantBucket)
    refund_by_key: dict[tuple[str, str, str], float] = defaultdict(float)
    income_by_key: dict[tuple[str, str, str], _MerchantBucket] = defaultdict(_MerchantBucket)

    for t in transactions:
        if t.is_transfer or t.date.year != year or t.date.month != month:
            continue
        category_main = t.category_main or "Sonstiges"
        category_sub = t.category_sub or ""
        merchant = t.merchant_canonical or t.merchant
        key = (category_main, category_sub, merchant)
        amount = round(abs(t.amount_chf), 2)

        if t.flow == "expense":
            bucket = expense_by_key[key]
            bucket.amount_chf += amount
            bucket.transactions.append(t)
            continue

        if _is_refund_income(t):
            refund_by_key[key] += amount
            continue

        bucket = income_by_key[key]
        bucket.amount_chf += amount
        bucket.transactions.append(t)

    merged: dict[tuple[str, str, str, str], _MerchantBucket] = {}
    for key, bucket in expense_by_key.items():
        refund = refund_by_key.get(key, 0.0)
        net = round(max(bucket.amount_chf - refund, 0.0), 2)
        if net <= 0:
            continue
        merged[("expense", *key)] = _MerchantBucket(amount_chf=net, transactions=bucket.transactions)
    for key, bucket in income_by_key.items():
        if bucket.amount_chf <= 0:
            continue
        merged[("income", *key)] = bucket
    return merged


def _summary(children: list[GraphNode], amount_chf: float, transaction_count: int) -> GraphSummary:
    avg = round(amount_chf / transaction_count, 2) if transaction_count else 0.0
    return GraphSummary(
        child_count=len(children),
        transaction_count=transaction_count,
        total_amount_chf=round(amount_chf, 2),
        avg_amount_chf=avg,
    )


def _delta(
    mode: GraphMode,
    node_flow: str,
    amount_chf: float,
    key: tuple[str, ...],
    baseline_totals: dict[tuple[str, ...], list[float]],
) -> GraphDelta | None:
    if mode != "delta":
        return None
    series = baseline_totals.get(key, [])
    if len(series) < _DELTA_MONTHS:
        return None
    baseline = round(median(series), 2)
    diff = round(amount_chf - baseline, 2)
    diff_pct = round((diff / baseline) * 100, 2) if baseline > 0 else None
    if abs(diff) < 0.01:
        direction = "neutral"
    elif node_flow == "expense":
        direction = "favourable" if diff < 0 else "unfavourable"
    else:
        direction = "favourable" if diff > 0 else "unfavourable"
    return GraphDelta(
        baseline_median_chf=baseline,
        diff_chf=diff,
        diff_pct=diff_pct,
        direction=direction,
    )


def _tx_leaf(t: Transaction, amount_chf: float) -> GraphNode:
    return GraphNode(
        id=t.id,
        label=t.merchant_canonical or t.merchant or "Transaction",
        level=3,
        node_type="transaction",
        flow=t.flow,  # type: ignore[arg-type]
        amount_chf=round(amount_chf, 2),
        transaction_count=1,
        category_main=t.category_main,
        category_sub=t.category_sub,
        merchant=t.merchant_canonical or t.merchant,
        children=None,
        transaction=TransactionPayload(
            id=t.id,
            date=t.date,
            value_date=t.value_date,
            merchant=t.merchant,
            merchant_canonical=t.merchant_canonical,
            original_description=t.text,
            amount_chf=round(abs(t.amount_chf), 2),
            flow=t.flow,  # type: ignore[arg-type]
            category_main=t.category_main,
            category_sub=t.category_sub,
            original_amount=t.original_amount,
            original_currency=t.original_currency,
            status=t.status,
        ),
    )


def _merchant_node(
    flow: str,
    category_main: str,
    category_sub: str,
    merchant: str,
    bucket: _MerchantBucket,
    rank: int | None,
    mode: GraphMode,
    baseline_totals: dict[tuple[str, ...], list[float]],
) -> GraphNode:
    txs = sorted(bucket.transactions, key=lambda t: (t.date, t.value_date, t.id))
    leaves = [_tx_leaf(t, round(abs(t.amount_chf), 2)) for t in txs]
    amount = round(bucket.amount_chf, 2)
    key = ("merchant", flow, category_main, category_sub, merchant)
    return GraphNode(
        id=f"merchant-{flow}-{category_main}-{category_sub}-{merchant}".replace(" ", "-").lower(),
        label=merchant or "Unbekannt",
        level=2,
        node_type="merchant",
        flow=flow,  # type: ignore[arg-type]
        amount_chf=amount,
        transaction_count=len(txs),
        rank=rank,
        category_main=category_main,
        category_sub=category_sub or None,
        merchant=merchant,
        children=leaves,
        delta=_delta(mode, flow, amount, key, baseline_totals),
        summary=_summary(leaves, amount, len(txs)),
    )


def _category_node(
    flow: str,
    category_main: str,
    category_sub: str,
    merchants: dict[str, _MerchantBucket],
    mode: GraphMode,
    baseline_totals: dict[tuple[str, ...], list[float]],
) -> GraphNode:
    merchant_items = sorted(merchants.items(), key=lambda kv: kv[1].amount_chf, reverse=True)
    top = merchant_items[:_TOP_MERCHANTS_PER_CATEGORY]
    rest = merchant_items[_TOP_MERCHANTS_PER_CATEGORY:]

    children = [
        _merchant_node(
            flow,
            category_main,
            category_sub,
            merchant,
            bucket,
            rank=idx + 1,
            mode=mode,
            baseline_totals=baseline_totals,
        )
        for idx, (merchant, bucket) in enumerate(top)
    ]

    if rest:
        other_transactions = [t for _, bucket in rest for t in bucket.transactions]
        other_amount = round(sum(bucket.amount_chf for _, bucket in rest), 2)
        other_children = [_tx_leaf(t, round(abs(t.amount_chf), 2)) for t in other_transactions]
        children.append(
            GraphNode(
                id=(
                    f"merchant-other-{flow}-{category_main}-{category_sub}".replace(" ", "-").lower()
                ),
                label="Other",
                level=2,
                node_type="merchant_group",
                flow=flow,  # type: ignore[arg-type]
                amount_chf=other_amount,
                transaction_count=len(other_transactions),
                merchant_count=len(rest),
                category_main=category_main,
                category_sub=category_sub or None,
                merchant="Other",
                children=other_children,
                summary=_summary(other_children, other_amount, len(other_transactions)),
            )
        )

    amount = round(sum(bucket.amount_chf for bucket in merchants.values()), 2)
    transaction_count = sum(len(bucket.transactions) for bucket in merchants.values())
    key = ("category", flow, category_main, category_sub)
    return GraphNode(
        id=f"category-{flow}-{category_main}-{category_sub}".replace(" ", "-").lower(),
        label=_category_label(category_main, category_sub),
        level=1,
        node_type="category",
        flow=flow,  # type: ignore[arg-type]
        amount_chf=amount,
        transaction_count=transaction_count,
        category_main=category_main,
        category_sub=category_sub or None,
        children=children,
        delta=_delta(mode, flow, amount, key, baseline_totals),
        summary=_summary(children, amount, transaction_count),
    )


def _flow_node(
    flow: str,
    flow_rows: list[tuple[str, str, str, str, _MerchantBucket]],
    mode: GraphMode,
    baseline_totals: dict[tuple[str, ...], list[float]],
) -> GraphNode:
    by_category: dict[tuple[str, str], dict[str, _MerchantBucket]] = defaultdict(dict)
    for _, category_main, category_sub, merchant, bucket in flow_rows:
        by_category[(category_main, category_sub)][merchant] = bucket

    categories = [
        _category_node(flow, category_main, category_sub, merchants, mode, baseline_totals)
        for (category_main, category_sub), merchants in by_category.items()
    ]
    categories.sort(key=lambda n: n.amount_chf, reverse=True)
    for i, node in enumerate(categories):
        node.rank = i + 1

    amount = round(sum(n.amount_chf for n in categories), 2)
    transaction_count = sum(n.transaction_count for n in categories)
    key = ("flow", flow)
    return GraphNode(
        id=f"flow-{flow}",
        label="Ausgaben" if flow == "expense" else "Einnahmen",
        level=0,
        node_type="flow",
        flow=flow,  # type: ignore[arg-type]
        amount_chf=amount,
        transaction_count=transaction_count,
        category_main=None,
        category_sub=None,
        children=categories,
        delta=_delta(mode, flow, amount, key, baseline_totals),
        summary=_summary(categories, amount, transaction_count),
    )


def _build_baseline_totals(
    transactions: list[Transaction], baseline_months: list[tuple[int, int]]
) -> dict[tuple[str, ...], list[float]]:
    per_month: list[dict[tuple[str, ...], float]] = []
    all_keys: set[tuple[str, ...]] = set()
    for year, month in baseline_months:
        buckets = _build_month_buckets(transactions, year, month)
        flow_totals: dict[str, float] = defaultdict(float)
        category_totals: dict[tuple[str, str, str], float] = defaultdict(float)
        month_totals: dict[tuple[str, ...], float] = {}
        for flow, category_main, category_sub, merchant in buckets:
            amount = buckets[(flow, category_main, category_sub, merchant)].amount_chf
            flow_totals[flow] += amount
            category_totals[(flow, category_main, category_sub)] += amount
            month_totals[("merchant", flow, category_main, category_sub, merchant)] = round(amount, 2)
        for flow, total in flow_totals.items():
            month_totals[("flow", flow)] = round(total, 2)
        for (flow, category_main, category_sub), total in category_totals.items():
            month_totals[("category", flow, category_main, category_sub)] = round(total, 2)
        per_month.append(month_totals)
        all_keys.update(month_totals.keys())

    totals: dict[tuple[str, ...], list[float]] = {}
    for key in all_keys:
        totals[key] = [month_totals.get(key, 0.0) for month_totals in per_month]
    return totals


def build_graph(
    transactions: list[Transaction],
    month: str,
    mode: GraphMode = "absolute",
    flow: GraphFlow = "expense",
) -> GraphResponse:
    year, mon = parse_month(month)
    baseline_months = _prev_months(year, mon, _DELTA_MONTHS)
    month_set = {(t.date.year, t.date.month) for t in transactions if not t.is_transfer}
    has_full_baseline = all(mk in month_set for mk in baseline_months)
    baseline_totals = _build_baseline_totals(transactions, baseline_months) if has_full_baseline else {}

    month_buckets = _build_month_buckets(transactions, year, mon)
    rows = [
        (flow_name, category_main, category_sub, merchant, bucket)
        for (flow_name, category_main, category_sub, merchant), bucket in month_buckets.items()
    ]

    flow_names = ["expense", "income"] if flow == "both" else [flow]
    flow_nodes = [
        _flow_node(flow_name, [r for r in rows if r[0] == flow_name], mode, baseline_totals)
        for flow_name in flow_names
    ]
    flow_nodes = [n for n in flow_nodes if n.amount_chf > 0]

    root_amount = round(sum(n.amount_chf for n in flow_nodes), 2)
    root_transactions = sum(n.transaction_count for n in flow_nodes)
    root = GraphNode(
        id="user-active",
        label="User",
        level=0,
        node_type="root",
        flow=None,
        amount_chf=root_amount,
        transaction_count=root_transactions,
        category_main=None,
        category_sub=None,
        children=flow_nodes,
        summary=_summary(flow_nodes, root_amount, root_transactions),
    )

    baseline_labels = [_month_key(y, m) for y, m in baseline_months]
    baseline_label = (
        f"verglichen mit dem Median {baseline_labels[0]}–{baseline_labels[-1]}"
        if has_full_baseline and len(baseline_labels) == _DELTA_MONTHS
        else None
    )
    return GraphResponse(
        month=month,
        mode=mode,
        flow=flow,
        baseline_months=baseline_labels,
        baseline_label=baseline_label,
        root=root,
    )


def flatten_graph_nodes(
    graph: GraphResponse,
    include_transactions: bool = False,
) -> list[SimpleNamespace]:
    rows: list[SimpleNamespace] = []

    def visit(node: GraphNode, parent_id: str | None):
        tx = node.transaction if include_transactions else None
        row = {
            "node_id": node.id,
            "parent_id": parent_id,
            "month": graph.month,
            "mode": graph.mode,
            "node_type": node.node_type,
            "level": node.level,
            "label": node.label,
            "flow": node.flow,
            "amount_chf": node.amount_chf,
            "transaction_count": node.transaction_count,
            "rank": node.rank,
            "merchant_count": node.merchant_count,
            "category_main": node.category_main,
            "category_sub": node.category_sub,
            "merchant": node.merchant,
            "has_children": bool(node.children),
            "delta_baseline_median_chf": node.delta.baseline_median_chf if node.delta else None,
            "delta_diff_chf": node.delta.diff_chf if node.delta else None,
            "delta_diff_pct": node.delta.diff_pct if node.delta else None,
            "delta_direction": node.delta.direction if node.delta else None,
            "summary_child_count": node.summary.child_count if node.summary else None,
            "summary_transaction_count": node.summary.transaction_count if node.summary else None,
            "summary_total_amount_chf": node.summary.total_amount_chf if node.summary else None,
            "summary_avg_amount_chf": node.summary.avg_amount_chf if node.summary else None,
            "tx_id": tx.id if tx else None,
            "tx_date": tx.date.isoformat() if tx else None,
            "tx_value_date": tx.value_date.isoformat() if tx else None,
            "tx_merchant": tx.merchant if tx else None,
            "tx_merchant_canonical": tx.merchant_canonical if tx else None,
            "tx_original_description": tx.original_description if tx else None,
            "tx_amount_chf": tx.amount_chf if tx else None,
            "tx_flow": tx.flow if tx else None,
            "tx_category_main": tx.category_main if tx else None,
            "tx_category_sub": tx.category_sub if tx else None,
            "tx_original_amount": tx.original_amount if tx else None,
            "tx_original_currency": tx.original_currency if tx else None,
            "tx_status": tx.status if tx else None,
        }
        rows.append(SimpleNamespace(**row))
        for child in node.children or []:
            visit(child, node.id)

    visit(graph.root, None)
    return rows