"""OData system query options for the `RecurringPayments` EntitySet (T9):
`$filter`, `$select`, `$orderby`, `$top`, `$skip`.

`$filter` is a hand-rolled recursive-descent parser rather than a
dependency on a third-party OData filter library: the practical subset
needed here (`eq`/`ne`/`gt`/`ge`/`lt`/`le`, `and`/`or`/`not`, parens,
string/number/bool/null literals) is small enough to implement directly
and verify completely - safer within a hackathon timeline than betting on
an unfamiliar package's exact API. NOT the full OData ABNF grammar: no
`contains`/`startswith`/other canonical functions, no arithmetic. Covers
what filtering RecurringPayments actually needs (e.g.
`$filter=is_active eq true and flow eq 'expense'`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

# --- tokenizer -----------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<string>'(?:[^']|'')*')
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<lparen>\()
      | (?P<rparen>\))
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)

_KEYWORDS = {"and", "or", "not", "eq", "ne", "gt", "ge", "lt", "le", "true", "false", "null"}


class ODataFilterError(ValueError):
    """Raised on malformed `$filter` syntax - callers (T10) should turn
    this into a 400 with the OData error envelope, not a 500."""


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                break
            raise ODataFilterError(f"Unexpected character at position {pos}: {text[pos:pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        value = m.group(kind)
        if kind == "ident" and value.lower() in _KEYWORDS:
            kind = value.lower()
        tokens.append((kind, value))
    return tokens


# --- AST -------------------------------------------------------------


@dataclass
class Comparison:
    field: str
    op: str
    value: Any


@dataclass
class BoolOp:
    op: str  # "and" | "or"
    left: Any
    right: Any


@dataclass
class Not:
    operand: Any


Node = "Comparison | BoolOp | Not"


class _Parser:
    """Recursive descent, grammar (highest to lowest precedence):
    literal := STRING | NUMBER | true | false | null
    comparison := IDENT (eq|ne|gt|ge|lt|le) literal | '(' or_expr ')'
    not_expr := 'not' not_expr | comparison
    and_expr := not_expr ('and' not_expr)*
    or_expr := and_expr ('or' and_expr)*
    """

    def __init__(self, tokens: list[tuple[str, str]]):
        self._tokens = tokens
        self._pos = 0

    def parse(self) -> Any:
        node = self._or_expr()
        if self._pos != len(self._tokens):
            raise ODataFilterError(f"Unexpected trailing tokens at {self._pos}")
        return node

    def _peek(self) -> tuple[str, str] | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self) -> tuple[str, str]:
        tok = self._peek()
        if tok is None:
            raise ODataFilterError("Unexpected end of $filter expression")
        self._pos += 1
        return tok

    def _or_expr(self) -> Any:
        node = self._and_expr()
        while (tok := self._peek()) and tok[0] == "or":
            self._advance()
            node = BoolOp("or", node, self._and_expr())
        return node

    def _and_expr(self) -> Any:
        node = self._not_expr()
        while (tok := self._peek()) and tok[0] == "and":
            self._advance()
            node = BoolOp("and", node, self._not_expr())
        return node

    def _not_expr(self) -> Any:
        if (tok := self._peek()) and tok[0] == "not":
            self._advance()
            return Not(self._not_expr())
        return self._comparison()

    def _comparison(self) -> Any:
        tok = self._peek()
        if tok and tok[0] == "lparen":
            self._advance()
            node = self._or_expr()
            closing = self._advance()
            if closing[0] != "rparen":
                raise ODataFilterError("Expected closing ')'")
            return node

        if not tok or tok[0] != "ident":
            raise ODataFilterError(f"Expected a field name, got {tok!r}")
        field = self._advance()[1]

        op_tok = self._advance()
        if op_tok[0] not in ("eq", "ne", "gt", "ge", "lt", "le"):
            raise ODataFilterError(f"Expected a comparison operator, got {op_tok!r}")

        value = self._literal()
        return Comparison(field, op_tok[0], value)

    def _literal(self) -> Any:
        tok = self._advance()
        kind, value = tok
        if kind == "string":
            return value[1:-1].replace("''", "'")
        if kind == "number":
            return float(value) if "." in value else int(value)
        if kind == "true":
            return True
        if kind == "false":
            return False
        if kind == "null":
            return None
        raise ODataFilterError(f"Expected a literal value, got {tok!r}")


def parse_filter(expression: str) -> Any:
    return _Parser(_tokenize(expression)).parse()


def _evaluate(node: Any, obj: Any) -> bool:
    if isinstance(node, Comparison):
        actual = getattr(obj, node.field, None)
        return _compare(actual, node.op, node.value)
    if isinstance(node, BoolOp):
        if node.op == "and":
            return _evaluate(node.left, obj) and _evaluate(node.right, obj)
        return _evaluate(node.left, obj) or _evaluate(node.right, obj)
    if isinstance(node, Not):
        return not _evaluate(node.operand, obj)
    raise ODataFilterError(f"Unknown AST node: {node!r}")


def _compare(actual: Any, op: str, expected: Any) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    # gt/ge/lt/le are meaningless across None/type mismatches - treat as
    # "doesn't match" rather than raising, so one odd field doesn't 500
    # the whole listing.
    if actual is None or expected is None or type(actual) is not type(expected):
        try:
            if actual is None or expected is None:
                return False
        except TypeError:
            return False
    try:
        if op == "gt":
            return actual > expected
        if op == "ge":
            return actual >= expected
        if op == "lt":
            return actual < expected
        if op == "le":
            return actual <= expected
    except TypeError:
        return False
    raise ODataFilterError(f"Unsupported operator: {op}")


# --- $select / $orderby / $top / $skip --------------------------------


def _apply_orderby(items: list[T], orderby: str) -> list[T]:
    clauses = [c.strip() for c in orderby.split(",") if c.strip()]
    # Stable sort, applied last-clause-first so the first clause wins ties.
    for clause in reversed(clauses):
        parts = clause.split()
        field = parts[0]
        desc = len(parts) > 1 and parts[1].lower() == "desc"
        items = sorted(
            items, key=lambda it: (getattr(it, field, None) is None, getattr(it, field, None)), reverse=desc
        )
    return items


def _apply_select(items: list[T], select: str) -> list[dict]:
    fields = [f.strip() for f in select.split(",") if f.strip()]
    return [{f: getattr(it, f, None) for f in fields} for it in items]


@dataclass
class QueryResult:
    items: list[Any]
    """Either the original typed items, or `dict`s if `$select` was used."""
    count: int
    """Total matching items after `$filter`, before `$top`/`$skip` -
    what `$count=true` reports."""


def _filter_fields(node: Any) -> set[str]:
    """All field names referenced anywhere in a `$filter` AST."""
    if isinstance(node, Comparison):
        return {node.field}
    if isinstance(node, BoolOp):
        return _filter_fields(node.left) | _filter_fields(node.right)
    if isinstance(node, Not):
        return _filter_fields(node.operand)
    return set()


def _check_fields(fields: set[str], allowed: frozenset[str], option: str) -> None:
    unknown = sorted(fields - allowed)
    if unknown:
        raise ODataFilterError(f"Unknown field in {option}: {', '.join(unknown)}")


def apply_query_options(
    items: list[T],
    filter_: str | None = None,
    select: str | None = None,
    orderby: str | None = None,
    top: int | None = None,
    skip: int | None = None,
    allowed_fields: frozenset[str] | None = None,
) -> QueryResult:
    """`allowed_fields` turns a typo'd field name into a 400 instead of a
    silently empty result or a `null` column - unknown fields in
    `$filter`/`$select`/`$orderby` raise `ODataFilterError`."""
    result: list[Any] = list(items)

    if allowed_fields is not None:
        if select:
            _check_fields({f.strip() for f in select.split(",") if f.strip()}, allowed_fields, "$select")
        if orderby:
            _check_fields(
                {c.strip().split()[0] for c in orderby.split(",") if c.strip()}, allowed_fields, "$orderby"
            )

    if filter_:
        ast = parse_filter(filter_)
        if allowed_fields is not None:
            _check_fields(_filter_fields(ast), allowed_fields, "$filter")
        result = [it for it in result if _evaluate(ast, it)]

    count = len(result)

    if orderby:
        result = _apply_orderby(result, orderby)
    if skip is not None:
        result = result[skip:]
    if top is not None:
        result = result[:top]
    if select:
        result = _apply_select(result, select)

    return QueryResult(items=result, count=count)
