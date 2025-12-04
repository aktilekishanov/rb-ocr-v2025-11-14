# src/test/unit/similarity_checker/test_null_handling.py
import pytest

from tests.unit.similarity_checker._assert import expect_identical, expect_different

# ---- Define all fields in your schema ----
ALL_FIELDS = [
    "CONTRACT_CURRENCY",
    "PAYMENT_CURRENCY",
    "CURRENCY_CONTRACT_NUMBER",
    "CONTRACT_AMOUNT_TYPE",
    "CONTRACT_DATE",
    "CONTRACT_END_DATE",
    "CLIENT",
    "CURRENCY_CONTRACT_TYPE_CODE",
    "COUNTERPARTY_NAME",
    "REPATRIATION_TERM",
    "COUNTERPARTY_COUNTRY",
    "AMOUNT",
]

# ---- Define null-like tokens commonly seen ----
NULL_STRINGS = [
    None,
    "",
    " ",
    "None",
    "none",
    "NULL",
    "null",
    "Null",
    "N/A",
    "NaN",
    "nan",
    "-",
    "—",
]

# ---- Core: targeted null/None scenarios per field ----

@pytest.mark.parametrize("field", ALL_FIELDS)
@pytest.mark.parametrize(
    "left,right,should_equal",
    [
        # Both null-like → should be treated as equal
        (None, None, True),
        ("None", None, True),
        ("null", "", True),

        # One side null-like, other has value → not equal
        (None, "something", False),
        ("", "value", False),
        ("null", "text", False),
        ("None", "ООО", False),
    ],
)
def test_null_and_nullstring_handling(compare_map, field, left, right, should_equal):
    """
    Ensure SimilarityChecker handles Python None and stringified nulls
    (like 'None', 'null', 'NaN', '-') consistently across all fields.
    """
    if should_equal:
        expect_identical(compare_map, field, left, right)
    else:
        expect_different(compare_map, field, left, right)


# ---- Exhaustive: every null-like vs every null-like should match ----

@pytest.mark.parametrize("field", ALL_FIELDS)
def test_all_null_variants_cross_equivalent(compare_map, field):
    """
    All null-like strings (None, 'None', 'null', 'NaN', '-', etc.)
    should compare as equivalent to each other.
    """
    for left in NULL_STRINGS:
        for right in NULL_STRINGS:
            # Using the helper gives a clean message with field/left/right/result map on failure
            expect_identical(compare_map, field, left, right)
