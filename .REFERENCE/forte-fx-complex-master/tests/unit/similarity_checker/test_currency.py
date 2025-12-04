import pytest
from tests.unit.similarity_checker._assert import expect_identical, expect_different


# ---------- Currency: single and lists, mixed types ----------

@pytest.mark.parametrize("field", ["CONTRACT_CURRENCY", "PAYMENT_CURRENCY"])
def test_currency_single_case_insensitive(compare_map, field):
    """Single currency comparison should be case-insensitive."""
    expect_identical(compare_map, field, "usd", "USD")


@pytest.mark.parametrize("field", ["CONTRACT_CURRENCY", "PAYMENT_CURRENCY"])
@pytest.mark.parametrize("a,b", [
    ("USD, EUR, KZT", "EUR USD KZT"),            # same set, diff separators
    (["usd", "EUR", "KZT"], ["KZT", "USD", "eur"]),  # list form
    ("USD, EUR, KZT", ["KZT", "EUR", "USD"]),    # string vs list
    ("USD,", "USD"),                             # trailing punctuation
])
def test_currency_lists_order_insensitive(compare_map, field, a, b):
    """Currency sets should match regardless of order, case, or punctuation."""
    expect_identical(compare_map, field, a, b)


@pytest.mark.parametrize("field", ["CONTRACT_CURRENCY", "PAYMENT_CURRENCY"])
@pytest.mark.parametrize("a,b", [
    ("USD, EUR", "USD"),       # missing one currency
    ("USD", "EUR"),            # completely different
    ("XXX", "USD"),            # invalid code ignored → sets differ
])
def test_currency_lists_negative(compare_map, field, a, b):
    """Different or incomplete currency sets should not be considered identical."""
    expect_different(compare_map, field, a, b)
