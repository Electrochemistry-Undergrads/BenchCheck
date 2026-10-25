import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchcheck.cv.parsing import parse_table  # noqa: E402
from benchcheck.models import AnalysisConfig  # noqa: E402

EXAMPLES = ROOT / "examples"


def example_config(example_id: str, **overrides) -> tuple[bytes, AnalysisConfig]:
    meta = json.loads((EXAMPLES / f"{example_id}.meta.json").read_text(encoding="utf-8"))
    raw = (EXAMPLES / meta["file"]).read_bytes()
    cfg = {
        "mapping": meta["mapping"],
        "units": meta["units"],
        "current_convention": meta["current_convention"],
        "metadata": meta["metadata"],
        "example_id": example_id,
    }
    cfg.update(overrides)
    return raw, AnalysisConfig(**cfg)


@pytest.fixture
def weak_example():
    return example_config("synthetic_lmo_weak_return")


@pytest.fixture
def clear_example():
    return example_config("synthetic_lmo_clear_return")


def table_from_text(text: str, name: str = "t.csv"):
    return parse_table(text.encode("utf-8"), name)
