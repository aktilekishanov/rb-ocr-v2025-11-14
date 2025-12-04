def expect_identical(compare_map, field, left, right):
    res = compare_map({field: left}, {field: right})
    ok = res.get(field)
    if ok is not True:
        msg = (
            "\n❌ Identical expected\n"
            f"  field: {field}\n"
            f"  left : {left!r}\n"
            f"  right: {right!r}\n"
            f"  result map: {res}\n"
        )
        raise AssertionError(msg)

def expect_different(compare_map, field, left, right):
    res = compare_map({field: left}, {field: right})
    ok = res.get(field)
    if ok is not False:
        msg = (
            "\n❌ Different expected\n"
            f"  field: {field}\n"
            f"  left : {left!r}\n"
            f"  right: {right!r}\n"
            f"  result map: {res}\n"
        )
        raise AssertionError(msg)
