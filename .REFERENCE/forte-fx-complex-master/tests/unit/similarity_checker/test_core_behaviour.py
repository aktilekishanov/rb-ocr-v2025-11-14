import pytest
from tests.unit.similarity_checker._assert import expect_identical


# ---------- Normalization: quotes / dashes / unicode spaces ----------

@pytest.mark.parametrize("field,left,right", [
    # Quotes (ASCII vs « » vs “ ”) → should be equivalent
    ("PRODUCT_NAME", '«ПРОДУКТ»', '"продукт"'),
    ("CLIENT",        'АО «ABC»', 'АО "ABC"'),
    ("COUNTERPARTY_NAME", '“ООО Ромашка”', '"ООО Ромашка"'),

    # Dashes (em/en/minus/non-breaking hyphen) → normalize to plain '-'
    ("PRODUCT_NAME", "А-Б—В–Г−Д", "А-Б-В-Г-Д"),  # mixed dash variants
    ("CLIENT",       'ООО "Ашан—Ойл"', 'ООО "Ашан-Ойл"'),

    # Unicode spaces (NBSP, thin space, etc.) → collapse to single ASCII space
    ("PRODUCT_NAME", "Коконы\u00A0урожая", "Коконы урожая"),       # NBSP
    ("PRODUCT_NAME", "Коконы\u2009урожая", "Коконы   урожая"),     # thin space vs many spaces

    # Dashes  mixed with spaces
    ("CURRENCY_CONTRACT_NUMBER", "Л - 01/25", "Л-01/25"),
])
def test_normalization_quotes_dashes_spaces(compare_map, field, left, right):
    """Quotes, dashes, and unicode spaces should normalize across all text-like fields."""
    expect_identical(compare_map, field, left, right)



def test_normalization_list_inputs_drop_nullish_entries(compare_map):
    """
    List inputs with nullish entries (None, '—', '', 'null') should be equivalent
    to the clean set without them.
    """
    dirty_list = ["USD", None, "—", "", "null", "Usd"]
    clean      = "USD"
    expect_identical(compare_map, "CONTRACT_CURRENCY", dirty_list, clean)
    expect_identical(compare_map, "PAYMENT_CURRENCY",  dirty_list, clean)


def test_normalization_soft_hyphen_removed(compare_map):
    """
    Soft hyphen (\u00AD) should be dropped → words equal with/without it.
    """
    left  = "ре\u00ADпатриация"   # re<soft hyphen>patriation
    right = "репатриация"
    expect_identical(compare_map, "REPATRIATION_TERM", left, right)
