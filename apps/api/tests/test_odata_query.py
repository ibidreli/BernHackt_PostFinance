"""Unit tests for the hand-rolled `$filter` parser and the other OData
query options in `app/odata/query.py` - pure functions, no app."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.odata.query import ODataFilterError, apply_query_options, parse_filter


def row(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


ROWS = [
    row(name="Migros", amount=12.5, active=True, category=None),
    row(name="O'Brien", amount=200.0, active=False, category="Food"),
    row(name="SBB", amount=3.7, active=True, category="Mobility"),
]


def names(result) -> list[str]:
    return [it.name for it in result.items]


# --- comparison operators ----------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("name eq 'Migros'", ["Migros"]),
        ("name ne 'Migros'", ["O'Brien", "SBB"]),
        ("amount gt 12.5", ["O'Brien"]),
        ("amount ge 12.5", ["Migros", "O'Brien"]),
        ("amount lt 12.5", ["SBB"]),
        ("amount le 12.5", ["Migros", "SBB"]),
        ("active eq true", ["Migros", "SBB"]),
        ("active eq false", ["O'Brien"]),
        ("category eq null", ["Migros"]),
        ("category ne null", ["O'Brien", "SBB"]),
    ],
)
def test_comparisons(expression, expected):
    assert names(apply_query_options(ROWS, filter_=expression)) == expected


def test_escaped_quote_in_string_literal():
    assert names(apply_query_options(ROWS, filter_="name eq 'O''Brien'")) == ["O'Brien"]


def test_and_binds_tighter_than_or():
    # a or (b and c), not (a or b) and c
    expression = "name eq 'SBB' or active eq false and amount gt 100"
    assert names(apply_query_options(ROWS, filter_=expression)) == ["O'Brien", "SBB"]


def test_parens_override_precedence():
    expression = "(name eq 'SBB' or active eq false) and amount gt 100"
    assert names(apply_query_options(ROWS, filter_=expression)) == ["O'Brien"]


def test_not_negates():
    assert names(apply_query_options(ROWS, filter_="not active eq true")) == ["O'Brien"]


def test_gt_across_type_mismatch_matches_nothing():
    assert names(apply_query_options(ROWS, filter_="name gt 5")) == []


# --- malformed expressions ---------------------------------------------


@pytest.mark.parametrize(
    "expression",
    [
        "name eq 'Migros' extra",  # trailing tokens
        "(name eq 'Migros'",  # unclosed paren
        "name eq",  # missing literal
        "eq 'Migros'",  # missing field
        "name like 'M%'",  # unsupported operator
        "name eq @foo",  # bad character
    ],
)
def test_malformed_filter_raises(expression):
    with pytest.raises(ODataFilterError):
        parse_filter(expression)


# --- $select / $orderby / $top / $skip / $count -------------------------


def test_orderby_desc_and_paging():
    result = apply_query_options(ROWS, orderby="amount desc", top=2, skip=1)
    assert names(result) == ["Migros", "SBB"]
    assert result.count == 3  # count is pre-paging


def test_select_projects_to_dicts():
    result = apply_query_options(ROWS, select="name,amount", top=1)
    assert result.items == [{"name": "Migros", "amount": 12.5}]


# --- allowed_fields strictness -----------------------------------------

FIELDS = frozenset({"name", "amount", "active", "category"})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"filter_": "typo eq 'x'"},
        {"filter_": "name eq 'Migros' and typo eq 'x'"},
        {"select": "name,typo"},
        {"orderby": "typo desc"},
    ],
)
def test_unknown_field_raises_with_allowed_fields(kwargs):
    with pytest.raises(ODataFilterError, match="Unknown field"):
        apply_query_options(ROWS, allowed_fields=FIELDS, **kwargs)


def test_known_fields_pass_with_allowed_fields():
    result = apply_query_options(
        ROWS, filter_="active eq true", select="name", orderby="amount", allowed_fields=FIELDS
    )
    assert result.items == [{"name": "SBB"}, {"name": "Migros"}]


def test_without_allowed_fields_unknown_names_stay_lenient():
    # Backwards-compatible default: no allow-list, no validation.
    assert names(apply_query_options(ROWS, filter_="typo eq 'x'")) == []
