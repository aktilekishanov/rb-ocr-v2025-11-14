import pytest

from tests.unit.similarity_checker._assert import expect_identical, expect_different


# ---------- Amount normalization ----------

@pytest.mark.parametrize("a,b", [
    ("780000,00", "780000.00"),
    ("780,000.00", "780000,00"),
    ("780000.0", "780000,0"),
    ("780 000,00", "780000.00"),
    (780000, "780000,00"),  # numeric vs string
])
def test_amount_equivalents(compare_map, a, b):
    """Different separators (comma/dot/space) or numeric type should match as equal amounts."""
    expect_identical(compare_map, "AMOUNT", a, b)


@pytest.mark.parametrize("a,b", [
    ("780000,00", "780100,00"),       # slightly different values
    ("not-a-number", "780000,00"),    # invalid value vs valid number
    ("780000,00", "not-a-number"),    # reverse invalid case
])
def test_amount_negative(compare_map, a, b):
    """Different numeric values or malformed numbers should not be considered identical."""
    expect_different(compare_map, "AMOUNT", a, b)
