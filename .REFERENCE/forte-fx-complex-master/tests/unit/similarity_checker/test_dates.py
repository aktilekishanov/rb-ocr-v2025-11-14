import pytest

from tests.unit.similarity_checker._assert import expect_identical, expect_different


# ---------- Date normalization ----------

# Positive cases for different date formats (equivalent representations)
@pytest.mark.parametrize("field", ["CONTRACT_DATE", "CONTRACT_END_DATE"])
@pytest.mark.parametrize("a,b", [
    ("2025-06-09", "09.06.2025"),
    ("31.12.2025", "2025-12-31"),
    ("20.12.2025", "20.12.2025"),  # identical format
])
def test_dates_equivalent_formats(compare_map, field, a, b):
    """Different date formats (ISO ↔ DD.MM.YYYY) should be considered identical."""
    expect_identical(compare_map, field, a, b)


# Negative cases for invalid or mismatched dates
@pytest.mark.parametrize("field", ["CONTRACT_DATE", "CONTRACT_END_DATE"])
@pytest.mark.parametrize("a,b", [
    ("2025-06-09", "10.06.2025"),    # one day off
    ("2025-12-31", "30.12.2025"),    # different day
    ("not-a-date", "31.12.2025"),    # malformed
    ("2025-06-09", "not-a-date"),    # malformed
    ("21.12.2025", "20.12.2025"),    # different date
])
def test_dates_negative_cases(compare_map, field, a, b):
    """Mismatched or malformed dates should not be considered identical."""
    expect_different(compare_map, field, a, b)
