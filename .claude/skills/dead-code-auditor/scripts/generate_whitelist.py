#!/usr/bin/env python3
"""Generate a project-specific whitelist by detecting common patterns.

This script auto-detects:
- Flyte task/workflow functions
- CLI entry points from pyproject.toml
- Pybind11 bindings (.so files)
- Plugin entry points

Usage:
    generate_whitelist.py [--output FILE] [--append]

Example:
    generate_whitelist.py  # Print to stdout
    generate_whitelist.py --output whitelist_auto.py
    generate_whitelist.py --append  # Append to whitelist.py
"""

import argparse
import ast
import re
import sys
from pathlib import Path

# Add script directory to path for config import
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import load_config

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


def find_flyte_tasks(config) -> list[tuple[str, str]]:
    """Find functions decorated with @task or @workflow."""
    results = []

    for source_dir in config.source_dirs:
        source_path = config.repo_root / source_dir
        if not source_path.exists():
            continue

        for py_file in source_path.rglob("*.py"):
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
            except (OSError, SyntaxError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    for decorator in node.decorator_list:
                        decorator_name = ""
                        if isinstance(decorator, ast.Name):
                            decorator_name = decorator.id
                        elif isinstance(decorator, ast.Call):
                            if isinstance(decorator.func, ast.Name):
                                decorator_name = decorator.func.id
                            elif isinstance(decorator.func, ast.Attribute):
                                decorator_name = decorator.func.attr

                        if decorator_name in ("task", "workflow", "dynamic"):
                            rel_path = py_file.relative_to(config.repo_root)
                            results.append((node.name, f"Flyte @{decorator_name} in {rel_path}"))

    return results


def find_cli_entry_points(config) -> list[tuple[str, str]]:
    """Find CLI entry points from pyproject.toml."""
    results = []
    pyproject = config.repo_root / "pyproject.toml"

    if not pyproject.exists():
        return results

    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return results

    # Check [project.scripts]
    scripts = data.get("project", {}).get("scripts", {})
    for name, entry in scripts.items():
        # entry is like "mypackage.cli:main"
        if ":" in entry:
            func_name = entry.split(":")[-1]
            results.append((func_name, f"CLI entry point: {name}"))

    # Check [project.gui-scripts]
    gui_scripts = data.get("project", {}).get("gui-scripts", {})
    for name, entry in gui_scripts.items():
        if ":" in entry:
            func_name = entry.split(":")[-1]
            results.append((func_name, f"GUI entry point: {name}"))

    # Check [project.entry-points]
    entry_points = data.get("project", {}).get("entry-points", {})
    for group, entries in entry_points.items():
        for name, entry in entries.items():
            if ":" in entry:
                func_name = entry.split(":")[-1]
                results.append((func_name, f"Entry point ({group}): {name}"))

    return results


def find_pybind_modules(config) -> list[tuple[str, str]]:
    """Find pybind11 module names from .so files."""
    results = []

    for source_dir in config.source_dirs:
        source_path = config.repo_root / source_dir
        if not source_path.exists():
            continue

        # Look for .so files (pybind11 modules)
        for so_file in source_path.rglob("*.so"):
            # Extract module name from filename like "module.cpython-311-darwin.so"
            name = so_file.stem
            if ".cpython" in name:
                name = name.split(".cpython")[0]
            results.append((name, f"Pybind11 module: {so_file.name}"))

    return results


def find_abstract_methods(config) -> list[tuple[str, str]]:
    """Find abstract methods that must be implemented by subclasses."""
    results = []

    for source_dir in config.source_dirs:
        source_path = config.repo_root / source_dir
        if not source_path.exists():
            continue

        for py_file in source_path.rglob("*.py"):
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
            except (OSError, SyntaxError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    for decorator in node.decorator_list:
                        decorator_name = ""
                        if isinstance(decorator, ast.Name):
                            decorator_name = decorator.id
                        elif isinstance(decorator, ast.Attribute):
                            decorator_name = decorator.attr

                        if decorator_name == "abstractmethod":
                            rel_path = py_file.relative_to(config.repo_root)
                            results.append((node.name, f"Abstract method in {rel_path}"))

    return results


def find_pytest_fixtures(config) -> list[tuple[str, str]]:
    """Find pytest fixtures in test directories."""
    results = []

    for test_dir in config.test_dirs:
        test_path = config.repo_root / test_dir
        if not test_path.exists():
            continue

        for py_file in test_path.rglob("*.py"):
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
            except (OSError, SyntaxError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        decorator_name = ""
                        if isinstance(decorator, ast.Name):
                            decorator_name = decorator.id
                        elif isinstance(decorator, ast.Call):
                            if isinstance(decorator.func, ast.Name):
                                decorator_name = decorator.func.id
                            elif isinstance(decorator.func, ast.Attribute):
                                decorator_name = decorator.func.attr

                        if decorator_name == "fixture":
                            results.append((node.name, "pytest fixture"))

    return results


def main():
    parser = argparse.ArgumentParser(description="Generate project-specific whitelist")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument(
        "--append",
        "-a",
        action="store_true",
        help="Append to existing whitelist.py",
    )

    args = parser.parse_args()

    try:
        config = load_config()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {config.repo_root.name}...", file=sys.stderr)

    all_entries = []

    # Detect patterns
    print("  Looking for Flyte tasks/workflows...", file=sys.stderr)
    flyte_entries = find_flyte_tasks(config)
    all_entries.extend(flyte_entries)
    print(f"    Found {len(flyte_entries)}", file=sys.stderr)

    print("  Looking for CLI entry points...", file=sys.stderr)
    cli_entries = find_cli_entry_points(config)
    all_entries.extend(cli_entries)
    print(f"    Found {len(cli_entries)}", file=sys.stderr)

    print("  Looking for pybind11 modules...", file=sys.stderr)
    pybind_entries = find_pybind_modules(config)
    all_entries.extend(pybind_entries)
    print(f"    Found {len(pybind_entries)}", file=sys.stderr)

    print("  Looking for abstract methods...", file=sys.stderr)
    abstract_entries = find_abstract_methods(config)
    all_entries.extend(abstract_entries)
    print(f"    Found {len(abstract_entries)}", file=sys.stderr)

    print("  Looking for pytest fixtures...", file=sys.stderr)
    fixture_entries = find_pytest_fixtures(config)
    all_entries.extend(fixture_entries)
    print(f"    Found {len(fixture_entries)}", file=sys.stderr)

    # Deduplicate by name
    seen = set()
    unique_entries = []
    for name, comment in all_entries:
        if name not in seen:
            seen.add(name)
            unique_entries.append((name, comment))

    # Generate output
    lines = [
        "# Auto-generated whitelist entries",
        f"# Generated for: {config.repo_root.name}",
        f"# Total entries: {len(unique_entries)}",
        "",
    ]

    # Group by category
    categories = {}
    for name, comment in unique_entries:
        category = comment.split(":")[0] if ":" in comment else comment.split(" in ")[0]
        if category not in categories:
            categories[category] = []
        categories[category].append((name, comment))

    for category, entries in sorted(categories.items()):
        lines.append(f"# {category}")
        for name, comment in sorted(entries):
            lines.append(f"{name}  # {comment}")
        lines.append("")

    output = "\n".join(lines)

    if args.append:
        whitelist_path = SCRIPT_DIR.parent / "whitelist.py"
        with open(whitelist_path, "a") as f:
            f.write("\n" + output)
        print(f"\nAppended {len(unique_entries)} entries to {whitelist_path}", file=sys.stderr)
    elif args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"\nWrote {len(unique_entries)} entries to {args.output}", file=sys.stderr)
    else:
        print(output)

    print(f"\nTotal unique entries: {len(unique_entries)}", file=sys.stderr)


if __name__ == "__main__":
    main()
