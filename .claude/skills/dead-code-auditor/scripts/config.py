#!/usr/bin/env python3
"""Configuration and auto-detection for dead code auditor.

This module handles:
- Finding the repository root
- Loading optional .dead-code-auditor.json config
- Auto-detecting Python source directories
- Auto-detecting test directories
- Finding all notebooks by extension
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Configuration for dead code auditor."""

    repo_root: Path
    source_dirs: list[str]
    exclude_dirs: list[str]
    exclude_patterns: list[str]
    ignored_decorators: list[str]
    ignored_names: list[str]

    # Derived paths
    notebook_paths: list[Path] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)


# Built-in exclusions
DEFAULT_EXCLUDE_DIRS = [
    "tests",
    "test",
    "__pycache__",
    "*.egg-info",
    "build",
    "dist",
    ".git",
    ".tox",
    ".venv",
    "venv",
    ".eggs",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
]

DEFAULT_IGNORED_DECORATORS = [
    "@pytest.fixture",
    "@pytest.mark.*",
    "@lru_cache",
    "@cached_property",
    "@property",
    "@staticmethod",
    "@classmethod",
    "@abstractmethod",
    "@overload",
    # Flyte
    "@task",
    "@workflow",
    "@dynamic",
    # Web frameworks
    "@app.route",
    "@app.get",
    "@app.post",
    "@app.put",
    "@app.delete",
    "@router.get",
    "@router.post",
    "@router.put",
    "@router.delete",
    # Click/Typer CLI
    "@click.command",
    "@click.group",
    "@app.command",
]

DEFAULT_IGNORED_NAMES = [
    "test_*",
    "*_fixture",
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "setUpModule",
    "tearDownModule",
    "_*",  # Private by convention
]


def find_repo_root(start_path: Path | None = None) -> Path:
    """Find the repository root by looking for common markers."""
    current = start_path or Path.cwd()
    markers = ["pyproject.toml", "setup.py", "setup.cfg", ".git"]

    while current != current.parent:
        for marker in markers:
            if (current / marker).exists():
                return current
        current = current.parent

    raise RuntimeError("Could not find repo root (no pyproject.toml, setup.py, or .git found)")


def detect_source_dirs(repo_root: Path) -> list[str]:
    """Auto-detect Python source directories.

    Looks for:
    1. Directories with __init__.py at repo root (Python packages)
    2. src/ directory with packages inside
    """
    source_dirs = []

    # Check for packages at repo root
    for item in repo_root.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            # Skip common non-source directories
            if item.name in DEFAULT_EXCLUDE_DIRS:
                continue
            if re.match(r"tests?_|_tests?$", item.name):
                continue
            # Check if it's a Python package
            if (item / "__init__.py").exists():
                source_dirs.append(item.name)

    # Check for src layout
    src_dir = repo_root / "src"
    if src_dir.exists():
        for item in src_dir.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                source_dirs.append(f"src/{item.name}")

    return source_dirs


def detect_test_dirs(repo_root: Path) -> list[str]:
    """Auto-detect test directories."""
    test_dirs = []
    patterns = ["tests", "test", "tests_*", "*_tests"]

    for item in repo_root.iterdir():
        if item.is_dir():
            for pattern in patterns:
                if pattern.endswith("*"):
                    if item.name.startswith(pattern[:-1]):
                        test_dirs.append(item.name)
                        break
                elif pattern.startswith("*"):
                    if item.name.endswith(pattern[1:]):
                        test_dirs.append(item.name)
                        break
                elif item.name == pattern:
                    test_dirs.append(item.name)
                    break

    return test_dirs


def find_notebooks(repo_root: Path, exclude_dirs: list[str] | None = None) -> list[Path]:
    """Find all Jupyter notebooks in the repository."""
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS

    notebooks = []
    for nb_path in repo_root.rglob("*.ipynb"):
        # Skip excluded directories
        rel_path = nb_path.relative_to(repo_root)
        parts = rel_path.parts

        skip = False
        for part in parts[:-1]:  # Check all parent dirs
            if part in exclude_dirs or part.startswith("."):
                skip = True
                break
            # Check glob patterns
            for excl in exclude_dirs:
                if "*" in excl and re.match(excl.replace("*", ".*"), part):
                    skip = True
                    break
            if skip:
                break

        if not skip:
            notebooks.append(nb_path)

    return sorted(notebooks)


def load_config(repo_root: Path | None = None, source_dirs: list[str] | None = None) -> Config:
    """Load configuration from file or auto-detect.

    Priority:
    1. Explicit source_dirs parameter
    2. .dead-code-auditor.json config file
    3. Auto-detection
    """
    if repo_root is None:
        repo_root = find_repo_root()

    # Try to load config file
    config_file = repo_root / ".dead-code-auditor.json"
    file_config = {}
    if config_file.exists():
        try:
            with open(config_file) as f:
                file_config = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Determine source directories
    if source_dirs:
        final_source_dirs = source_dirs
    elif "source_dirs" in file_config:
        final_source_dirs = file_config["source_dirs"]
    else:
        final_source_dirs = detect_source_dirs(repo_root)

    if not final_source_dirs:
        raise RuntimeError(
            "No Python source directories found. "
            "Either create a package with __init__.py or specify --source-dirs"
        )

    # Build exclude directories list
    exclude_dirs = list(DEFAULT_EXCLUDE_DIRS)
    if "exclude_dirs" in file_config:
        exclude_dirs.extend(file_config["exclude_dirs"])

    # Add detected test dirs to exclusions
    test_dirs = detect_test_dirs(repo_root)
    exclude_dirs.extend(test_dirs)

    # Build exclude patterns
    exclude_patterns = file_config.get("exclude_patterns", [])

    # Build ignored decorators
    ignored_decorators = list(DEFAULT_IGNORED_DECORATORS)
    if "extra_ignored_decorators" in file_config:
        ignored_decorators.extend(file_config["extra_ignored_decorators"])

    # Build ignored names
    ignored_names = list(DEFAULT_IGNORED_NAMES)
    if "extra_ignored_names" in file_config:
        ignored_names.extend(file_config["extra_ignored_names"])

    # Find notebooks
    notebooks = find_notebooks(repo_root, exclude_dirs)

    return Config(
        repo_root=repo_root,
        source_dirs=final_source_dirs,
        exclude_dirs=list(set(exclude_dirs)),  # Deduplicate
        exclude_patterns=exclude_patterns,
        ignored_decorators=ignored_decorators,
        ignored_names=ignored_names,
        notebook_paths=notebooks,
        test_dirs=test_dirs,
    )


def get_vulture_exclude_string(config: Config) -> str:
    """Generate vulture --exclude argument string."""
    return ",".join(config.exclude_dirs)


def get_vulture_ignore_decorators_string(config: Config) -> str:
    """Generate vulture --ignore-decorators argument string."""
    return ",".join(config.ignored_decorators)


def get_vulture_ignore_names_string(config: Config) -> str:
    """Generate vulture --ignore-names argument string."""
    return ",".join(config.ignored_names)


if __name__ == "__main__":
    # Test auto-detection
    config = load_config()
    print(f"Repo root: {config.repo_root}")
    print(f"Source dirs: {config.source_dirs}")
    print(f"Test dirs: {config.test_dirs}")
    print(f"Exclude dirs: {config.exclude_dirs}")
    print(f"Notebooks found: {len(config.notebook_paths)}")
    for nb in config.notebook_paths[:5]:
        print(f"  - {nb.relative_to(config.repo_root)}")
    if len(config.notebook_paths) > 5:
        print(f"  ... and {len(config.notebook_paths) - 5} more")
