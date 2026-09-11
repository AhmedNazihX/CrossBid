"""The suite's one structural rule: a test module imports no other test module.

It is a rule about what the security tests prove. The recording connection fake, the fake
pool and the pipeline fakes are where tenant scope, DSN redaction and failure-reason leakage
are asserted, and a fake that lives in a test module belongs to that module's story: its
owner may reshape it for the next acceptance criterion and silently change what somebody
else's test proves. That is not hypothetical — `FakeConnectionSource` existed twice, in two
incompatible shapes, and which one a tenant-scope test asserted through was decided by which
module its author had happened to read.

So `conftest.py` is the shared ground, and this walks the source to say so. A helper needed
twice moves there; a helper needed once stays where it is used.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent.parent
SHARED_GROUND = "tests.conftest"

MODULES = sorted(path for path in TESTS_DIR.rglob("*.py") if path.name != "conftest.py")


def _imported(path: Path) -> set[str]:
    """Every module name the file imports, relative imports included as written."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.name)
def test_a_test_module_imports_no_other_test_module(path: Path) -> None:
    """Anything two modules need is in `conftest.py`; nothing else under `tests/` is shared."""
    # Act
    borrowed = {
        name
        for name in _imported(path)
        if (name.startswith(("tests.", ".")) and name != SHARED_GROUND)
        or any(part.startswith("test_") for part in name.split("."))
    }

    # Assert
    assert borrowed == set(), (
        f"{path.name} imports {sorted(borrowed)}. A fake or fixture that two modules need "
        f"belongs in {SHARED_GROUND}, where one definition serves the whole suite."
    )


def test_the_walk_actually_found_the_test_modules() -> None:
    """Guards the guard: an empty file list would make every assertion above vacuous."""
    # Assert
    assert len(MODULES) > 40
    assert TESTS_DIR / "unit" / "test_companies_readmodel.py" in MODULES
