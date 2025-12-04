import pytest

from tests.unit.similarity_checker._assert import expect_identical, expect_different

# Fields likely to behave as string↔list
FIELDS_WITH_LISTLIKE_BEHAVIOUR = [
    "CONTRACT_CURRENCY",
    "PAYMENT_CURRENCY",
    "CONTRACT_NAMES",
    "DOCUMENT_REFERENCES",
]

@pytest.mark.parametrize("field", FIELDS_WITH_LISTLIKE_BEHAVIOUR)
@pytest.mark.parametrize(
    "left,right,should_equal",
    [
        # string ↔ list with same items
        ("abc, bcd", ["abc", "bcd"], True),

        # trailing null-like element should not break equality
        ("abc, bcd, null", ["abc", "bcd", None], True),
        ("abc, bcd", ["abc", "bcd", "null"], True),

        # extra real value should make them different
        ("abc, bcd", ["null", "bcd", "xyz"], False),
        ("abc, bcd", ["abc", "null"], False),

        # one side empty / null
        ("abc, bcd", [], False),
        ("", ["abc"], False),
        (None, ["abc"], False),
    ],
)
def test_string_vs_list_with_null_tokens(compare_map, field, left, right, should_equal):
    """
    Verify that comma-separated strings and lists normalize consistently.
    Null-like tokens in lists ('null', None) should be ignored.
    Extra meaningful elements must cause mismatch.
    """
    if should_equal:
        expect_identical(compare_map, field, left, right)
    else:
        expect_different(compare_map, field, left, right)
