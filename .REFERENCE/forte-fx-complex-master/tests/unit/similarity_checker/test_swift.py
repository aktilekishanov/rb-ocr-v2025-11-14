from tests.unit.similarity_checker._assert import expect_identical


# ---------- BIK/SWIFT string normalization (spaces / commas) ----------

def test_bik_swift_spacing_punctuation(compare_map):
    """BIK/SWIFT values should be equivalent regardless of spaces or commas."""
    left = "IRTYKZKA, HSBKKZKX, KZKOTJ22XXX"
    right = "IRTYKZKA,HSBKKZKX,KZKOTJ22XXX"
    expect_identical(compare_map, "BIK_SWIFT", left, right)
