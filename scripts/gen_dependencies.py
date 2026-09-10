#!/usr/bin/env python3
"""Generate `dependencies.txt` from the two lock files.

One manifest of every third-party package in the repository, both apps, so a reviewer can
see the whole dependency surface without opening a lock file. Reads `backend/uv.lock` and
`frontend/package-lock.json`; writes `dependencies.txt` at the repository root.

`dependencies.txt` is GENERATED. Never edit it by hand (rule in CLAUDE.md) — run
`make deps`, or `python3 scripts/gen_dependencies.py`.

    python3 scripts/gen_dependencies.py           # write the manifest
    python3 scripts/gen_dependencies.py --check    # exit 1 if it is stale, print a diff

Standard library only, so it runs with any Python 3.11+ without installing anything.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UV_LOCK = ROOT / "backend" / "uv.lock"
NPM_LOCK = ROOT / "frontend" / "package-lock.json"
BACKEND_PYPROJECT = ROOT / "backend" / "pyproject.toml"
FRONTEND_PACKAGE = ROOT / "frontend" / "package.json"
MANIFEST = ROOT / "dependencies.txt"

HEADER = """# Dependency manifest — GENERATED, DO NOT EDIT BY HAND.
#
# Regenerate with `make deps` (or `python3 scripts/gen_dependencies.py`) after ANY
# dependency change. `make lint` fails if this file has drifted from the lock files.
#
# Sources: backend/uv.lock, frontend/package-lock.json
# Scope:   direct = declared in pyproject.toml / package.json
#          transitive = pulled in by a direct dependency
#          dev = build, lint, test, or type-check tooling only
#
# {total} packages: {backend_count} backend, {frontend_count} frontend
"""

NPM_PREFIX = "node_modules/"


@dataclass(frozen=True, order=True)
class Package:
    """One resolved third-party package. Ordered so output is deterministic."""

    app: str
    name: str
    version: str
    scope: str


def _normalise(name: str) -> str:
    """PEP 503 normalisation, so `Foo.Bar_baz` and `foo-bar-baz` compare equal."""
    return name.lower().replace("_", "-").replace(".", "-")


def read_backend() -> list[Package]:
    """Every package resolved in uv.lock, tagged direct/transitive/dev."""
    lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    pyproject = tomllib.loads(BACKEND_PYPROJECT.read_text(encoding="utf-8"))
    project = pyproject.get("project", {})

    def bare(spec: str) -> str:
        """`fastapi[std]>=0.115` -> `fastapi`."""
        for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
            spec = spec.split(sep)[0]
        return _normalise(spec.strip())

    direct = {bare(s) for s in project.get("dependencies", [])}
    dev = {
        bare(s)
        for group in project.get("optional-dependencies", {}).values()
        for s in group
    }
    # The project itself is not a third-party dependency.
    own_name = _normalise(project.get("name", ""))

    packages: list[Package] = []
    for entry in lock.get("package", []):
        name = entry.get("name", "")
        version = entry.get("version", "")
        if not name or not version or _normalise(name) == own_name:
            continue
        key = _normalise(name)
        if key in dev:
            scope = "dev"
        elif key in direct:
            scope = "direct"
        else:
            scope = "transitive"
        packages.append(Package("backend", name, version, scope))
    return packages


def read_frontend() -> list[Package]:
    """Every package in package-lock.json, tagged direct/transitive/dev."""
    lock = json.loads(NPM_LOCK.read_text(encoding="utf-8"))
    manifest = json.loads(FRONTEND_PACKAGE.read_text(encoding="utf-8"))
    direct = set(manifest.get("dependencies", {}))
    dev_direct = set(manifest.get("devDependencies", {}))

    packages: list[Package] = []
    for path, meta in lock.get("packages", {}).items():
        if not path.startswith(NPM_PREFIX):
            continue  # the root project entry has an empty key
        # Nested installs look like `node_modules/a/node_modules/b`; the real name is the last.
        name = path.rsplit(NPM_PREFIX, 1)[-1]
        version = meta.get("version", "")
        if not version:
            continue  # link/workspace entries carry no version
        if name in dev_direct or meta.get("dev"):
            scope = "dev"
        elif name in direct:
            scope = "direct"
        else:
            scope = "transitive"
        packages.append(Package("frontend", name, version, scope))
    return packages


def render(packages: list[Package]) -> str:
    """Deterministic text: fixed header, stable sort, one package per line."""
    unique = sorted(set(packages))
    backend = [p for p in unique if p.app == "backend"]
    frontend = [p for p in unique if p.app == "frontend"]
    width = max((len(p.name) for p in unique), default=0)

    lines = [
        HEADER.format(
            total=len(unique),
            backend_count=len(backend),
            frontend_count=len(frontend),
        )
    ]
    for app, group in (("backend", backend), ("frontend", frontend)):
        lines.append(f"\n## {app} ({len(group)})\n")
        lines.extend(
            f"{p.name:<{width}}  {p.version:<14}  {p.scope}" for p in group
        )
    return "\n".join(lines).rstrip() + "\n"


def missing_locks() -> list[str]:
    return [
        str(path.relative_to(ROOT))
        for path in (UV_LOCK, BACKEND_PYPROJECT, NPM_LOCK, FRONTEND_PACKAGE)
        if not path.is_file()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if dependencies.txt is stale; print a diff instead of writing",
    )
    args = parser.parse_args()

    absent = missing_locks()
    if absent:
        print(
            "cannot generate the dependency manifest, these files are missing:\n"
            + "\n".join(f"  - {name}" for name in absent)
            + "\nRun `uv sync` in backend/ and `npm install` in frontend/ first.",
            file=sys.stderr,
        )
        return 1

    expected = render(read_backend() + read_frontend())

    if not args.check:
        MANIFEST.write_text(expected, encoding="utf-8")
        count = expected.count("\n")
        print(f"wrote {MANIFEST.relative_to(ROOT)} ({count} lines)")
        return 0

    actual = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else ""
    if actual == expected:
        print("dependencies.txt is up to date")
        return 0

    diff = difflib.unified_diff(
        actual.splitlines(keepends=True),
        expected.splitlines(keepends=True),
        fromfile="dependencies.txt (committed)",
        tofile="dependencies.txt (expected)",
    )
    sys.stderr.writelines(diff)
    print(
        "\ndependencies.txt is stale. Run `make deps` and commit the result.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
