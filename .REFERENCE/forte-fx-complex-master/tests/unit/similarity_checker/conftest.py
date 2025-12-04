import pytest

from src.common.similarity_check.similarity_checker import SimilarityChecker


# ============================== INITIALIZE HELPERS ==================================

def to_result_map(list_result):
    """
    Convert the SimilarityChecker output:
        [{"name": "FIELD", "Identical": True/False}, ...]
    into a dict: {"FIELD": True/False, ...}
    Unknown/missing fields can be checked with res.get(key, False).
    """
    if not isinstance(list_result, (list, tuple)):
        raise TypeError(f"Expected list result, got {type(list_result)}")
    mapping = {}
    for item in list_result:
        if isinstance(item, dict) and "name" in item:
            mapping[str(item["name"])] = bool(item.get("Identical"))
    return mapping


@pytest.fixture
def cmp():
    # Arrange: common test subject
    return SimilarityChecker(debug=True)


@pytest.fixture
def compare_map(cmp):
    """
    Call comparator and always get a {field: bool} map back.
    Use this fixture in tests instead of calling cmp.compare directly.
    """
    def _run(a, b):
        raw = cmp.compare(a, b)
        return to_result_map(raw)
    return _run


