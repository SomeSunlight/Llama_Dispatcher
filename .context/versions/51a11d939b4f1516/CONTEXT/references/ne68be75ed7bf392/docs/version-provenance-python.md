# Python runtime version provenance

Use this pattern when a Python CLI is actively tested from editable Git checkouts and the release version alone is too ambiguous.

The goal is to keep two identities separate:

- **Release version** — the stable package/release baseline, for example `0.10.0`.
- **Development provenance** — the exact checkout currently executing, for example `issue-79-version-provenance@23d1c69` or `main@f2d3679, dirty`.

The commit SHA is the immutable identity. The branch/ref is only human orientation.

## Recommended output

Source/editable checkout:

```text
toolname 0.10.0 (feature/my-change@abc1234)
```

Dirty checkout:

```text
toolname 0.10.0 (feature/my-change@abc1234, dirty)
```

Detached checkout, for example in CI:

```text
toolname 0.10.0 (detached@abc1234)
```

Installed release artifact without an enclosing Git checkout:

```text
toolname 0.10.0
```

Do not encode the branch into the release version and do not bump the release version merely because another development branch exists.

## Keep one release-version source

For a normal `pyproject.toml` project, keep the canonical release version there:

```toml
[project]
name = "toolname"
version = "0.10.0"
```

Do not duplicate the literal version in `version.py`. In a source/editable checkout, read `pyproject.toml` so a pulled version change is visible immediately without reinstalling. For an installed artifact, fall back to `importlib.metadata.version()`.

## Small dependency-free implementation

Adapt the distribution name and project-root detection to the project:

```python
from __future__ import annotations

import subprocess
import tomllib
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path

_DISTRIBUTION_NAME = "toolname"


def _project_root(start: Path | None = None) -> Path | None:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if project.get("name") == _DISTRIBUTION_NAME:
            return candidate
    return None


def _pyproject_version(root: Path) -> str | None:
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return None

    value = project.get("version")
    return value if isinstance(value, str) and value else None


def release_version(project_root: Path | None = None) -> str:
    root = project_root or _project_root()
    if root is not None:
        value = _pyproject_version(root)
        if value is not None:
            return value

    try:
        return distribution_version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "unknown"


def _git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def git_provenance(project_root: Path | None = None) -> str | None:
    root = project_root or _project_root()
    if root is None or not (root / ".git").exists():
        return None

    commit = _git(root, "rev-parse", "--short=7", "HEAD")
    if not commit:
        return None

    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD") or "detached"
    status = _git(root, "status", "--porcelain", "--untracked-files=normal")

    result = f"{branch}@{commit}"
    if status:
        result += ", dirty"
    return result


def display_version(project_root: Path | None = None) -> str:
    release = release_version(project_root)
    provenance = git_provenance(project_root)
    return f"{release} ({provenance})" if provenance else release


__version__ = release_version()
```

This intentionally shells out to Git only when version/provenance is requested. Normal program operations should not pay that cost.

## argparse integration

A custom action lets `--version` compute the checkout identity at invocation time instead of freezing it when the parser is constructed or the package is installed:

```python
class _RuntimeVersionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None) -> None:
        parser._print_message(f"{parser.prog} {display_version()}\n", sys.stdout)
        parser.exit()


parser.add_argument("--version", action=_RuntimeVersionAction, nargs=0)
```

Keep `--version` on stdout, matching normal CLI expectations.

## Focused tests

At minimum verify:

1. `release_version()` reads the value from the checkout's `pyproject.toml`.
2. A non-Git source tree returns the plain release version.
3. A temporary Git repository returns `branch@short-sha`.
4. A modified tracked file adds `, dirty`.
5. Detached HEAD reports `detached@short-sha`.
6. CLI `--version` exits successfully and writes to stdout.

Prefer creating a real temporary Git repository in the test rather than mocking Git output; the behavior being tested is small and deterministic.

## When not to create a shared library

For this pattern the code is deliberately small and project integration differs in distribution name, root detection, CLI framework, and test layout. Copying/adapting the reference is usually simpler than adding a runtime dependency.

A shared library becomes worthwhile only if several projects need materially more behavior such as tag-derived release versions, build metadata injection, non-Git VCS support, or a centrally maintained compatibility contract.
