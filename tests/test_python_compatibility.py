"""Guard runtime syntax separately from the newer development interpreter."""

import ast
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "homewizard_legacy"


@pytest.mark.parametrize("source", sorted(INTEGRATION.rglob("*.py")), ids=lambda p: p.name)
def test_integration_parses_on_python_313(source):
    ast.parse(source.read_text(encoding="utf-8"), filename=str(source), feature_version=(3, 13))
