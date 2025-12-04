import pytest
import yaml
from pathlib import Path
from hypothesis import given, settings, strategies as st

from tests.unit.similarity_checker._assert import expect_identical, expect_different

# Which fields are organization-like in your checker:
ORG_FIELDS_ALL = ["CLIENT", "COUNTERPARTY_NAME"]
ORG_FIELDS_POS_ONLY = ["CLIENT", "COUNTERPARTY_NAME"]  # widen to ALL when your checker supports every field

# --- helpers to load YAML tables ---

def _load_cases(filename: str):
    data_dir = Path(__file__).parent / "data"
    rows = yaml.safe_load((data_dir / filename).read_text(encoding="utf-8"))
    # return triples (left, right, label)
    return [(r["left"], r["right"], r["label"]) for r in rows]

POS = _load_cases("org_positive.yaml")
NEG = _load_cases("org_negative.yaml")

# ids for nice pytest output
POS_IDS = [label for *_ignore, label in POS]
NEG_IDS = [label for *_ignore, label in NEG]

# ---------- YAML-driven example tests ----------

@pytest.mark.parametrize("field", ORG_FIELDS_POS_ONLY)
@pytest.mark.parametrize("left,right,label", POS, ids=POS_IDS)
def test_org_aliases_positive(compare_map, field, left, right, label):
    expect_identical(compare_map, field, left, right)


@pytest.mark.parametrize("field", ORG_FIELDS_ALL)
@pytest.mark.parametrize("left,right,label", NEG, ids=NEG_IDS)
def test_org_aliases_negative(compare_map, field, left, right, label):
    expect_different(compare_map, field, left, right)



# ---------- Hypothesis property tests ----------
