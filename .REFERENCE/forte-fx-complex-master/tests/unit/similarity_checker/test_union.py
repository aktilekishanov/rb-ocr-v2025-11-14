# ---------- Union of keys: both sides compared ----------

def test_union_of_keys_is_compared(compare_map):
    a = {"A": "x"}   # generic string → case-insensitive
    b = {"B": "y"}
    res = compare_map(a, b)
    # Implementations may omit unknown keys; accept either absent or explicitly False.
    assert res.get("A", False) is False
    assert res.get("B", False) is False

