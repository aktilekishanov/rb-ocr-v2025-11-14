import pytest

from tests.unit.similarity_checker._assert import expect_identical, expect_different


# ---------- General strings: case / whitespace / quotes ----------

@pytest.mark.parametrize("a,b", [
    ('Договор на поставку', 'договор  на  поставку'),
    ('«ПРОДУКТ»', '"продукт"'),
    ("  Коконы урожая  ", "коконы   урожая"),
])
def test_generic_strings_normalization(compare_map, a, b):
    """Strings differing only by case, quotes, or spacing should be identical."""
    expect_identical(compare_map, "PRODUCT_NAME", a, b)


def test_generic_strings_negative(compare_map):
    """Different words should not be considered identical."""
    expect_different(compare_map, "PRODUCT_NAME", "Коконы  урожая", "Коконы шелка")
