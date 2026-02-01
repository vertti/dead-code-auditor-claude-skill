#!/usr/bin/env python3
"""Verify whether a candidate is truly dead code.

This script performs thorough verification using grep/ripgrep searches to
determine if a code element is truly unused.

Usage:
    verify_candidate.py <name> <file_path> [--verbose] [--json]
    verify_candidate.py <name> <file_path> --source-dirs src mypackage

Example:
    verify_candidate.py unused_func src/utils/foo.py
    verify_candidate.py MyClass mypackage/models/bar.py --verbose
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Add script directory to path for config import
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import Config, load_config


def run_rg(pattern: str, paths: list[str], extra_args: list[str] | None = None) -> list[str]:
    """Run ripgrep and return matching lines."""
    if extra_args is None:
        extra_args = []

    # Filter to existing paths
    existing_paths = [p for p in paths if Path(p).exists()]
    if not existing_paths:
        return []

    cmd = ["rg", pattern, *existing_paths, *extra_args, "--no-heading", "-n"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return [line for line in result.stdout.strip().split("\n") if line]
        return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def is_definition_line(line: str, name: str) -> bool:
    """Check if a line is the definition of the name (not a usage)."""
    patterns = [
        rf"^\s*def\s+{re.escape(name)}\s*\(",  # function def
        rf"^\s*async\s+def\s+{re.escape(name)}\s*\(",  # async function def
        rf"^\s*class\s+{re.escape(name)}\s*[:\(]",  # class def
        rf"^\s*{re.escape(name)}\s*=",  # variable assignment
        rf"^\s*{re.escape(name)}\s*:",  # type annotation (dataclass field)
    ]
    for pattern in patterns:
        if re.search(pattern, line):
            return True
    return False


def is_test_path(file_path: str, config: Config) -> bool:
    """Check if a file path is in a test directory."""
    path_parts = Path(file_path).parts
    for test_dir in config.test_dirs:
        if test_dir in path_parts:
            return True
    # Also check common patterns
    for part in path_parts:
        if re.match(r"tests?$|tests?_|_tests?$", part):
            return True
    return False


def verify_candidate(
    name: str,
    file_path: str,
    config: Config,
    verbose: bool = False,
) -> dict:
    """
    Verify if a candidate is truly dead code.

    Returns a dict with:
        - is_dead: bool - True if no references found
        - references: list[str] - References found (if any)
        - verification_details: list[str] - What checks were performed
        - notebook_only: bool - True if only used in notebooks
    """
    references = []
    notebook_references = []
    verification_details = []

    repo_root = config.repo_root

    # Build source paths
    source_paths = [str(repo_root / d) for d in config.source_dirs]

    # Get the file containing the definition to exclude it
    def_file = str(repo_root / file_path) if file_path else None

    # 1. Search for name in source code
    verification_details.append(f'Search: rg "{name}" {" ".join(config.source_dirs)} --type py')
    matches = run_rg(name, source_paths, ["--type", "py"])

    for match in matches:
        parts = match.split(":", 2)
        if len(parts) >= 3:
            match_file, line_num, line_content = parts[0], parts[1], parts[2]

            # Skip if this is the definition itself
            if def_file and Path(match_file).resolve() == Path(def_file).resolve():
                if is_definition_line(line_content, name):
                    continue

            # Skip test files
            if is_test_path(match_file, config):
                continue

            # Skip if it's in a comment
            stripped = line_content.strip()
            if stripped.startswith("#"):
                continue

            references.append(match)

    # 2. Search in notebooks (by extension)
    verification_details.append(f'Search: rg "{name}" --glob "*.ipynb"')
    if config.notebook_paths:
        # Search in directories containing notebooks
        notebook_dirs = list(set(str(nb.parent) for nb in config.notebook_paths))
        matches = run_rg(name, notebook_dirs, ["--glob", "*.ipynb"])
        notebook_references.extend(matches)

    # 3. Search for string literal references (dynamic dispatch)
    verification_details.append(f'Search: rg \'"{name}"|' + f"'{name}'\" in source")
    string_matches = run_rg(f'"{name}"|' + f"'{name}'", source_paths)
    for match in string_matches:
        parts = match.split(":", 2)
        if len(parts) >= 3:
            match_file = parts[0]
            if not is_test_path(match_file, config):
                references.append(f"[string ref] {match}")

    # 4. Check __init__.py re-exports
    verification_details.append("Search: Check __init__.py files for re-exports")
    for source_dir in config.source_dirs:
        source_path = repo_root / source_dir
        if source_path.exists():
            for init_file in source_path.rglob("__init__.py"):
                try:
                    content = init_file.read_text()
                    if re.search(rf"\bimport\s+{re.escape(name)}\b", content):
                        references.append(f"[re-export] {init_file}:import {name}")
                    if re.search(rf'["\']' + re.escape(name) + r'["\']', content):
                        if "__all__" in content:
                            references.append(f"[__all__] {init_file}")
                except (OSError, UnicodeDecodeError):
                    continue

    # 5. Check for inheritance/method override patterns (for classes)
    if name[0].isupper():
        verification_details.append(f"Search: Check for class inheritance ({name})")
        inheritance_matches = run_rg(
            rf"\({name}\)|\({name},|,\s*{name}\)", source_paths, ["--type", "py"]
        )
        for match in inheritance_matches:
            parts = match.split(":", 2)
            if len(parts) >= 3:
                match_file = parts[0]
                if not is_test_path(match_file, config):
                    references.append(f"[inheritance] {match}")

    # Determine final status
    is_dead = len(references) == 0
    notebook_only = is_dead and len(notebook_references) > 0

    return {
        "name": name,
        "file_path": file_path,
        "is_dead": is_dead,
        "notebook_only": notebook_only,
        "references": references,
        "notebook_references": notebook_references,
        "verification_details": verification_details,
    }


def main():
    parser = argparse.ArgumentParser(description="Verify if a candidate is truly dead code")
    parser.add_argument("name", help="Name of the function/class/variable to verify")
    parser.add_argument("file_path", help="Path to the file containing the definition")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed verification steps")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--source-dirs",
        nargs="+",
        help="Source directories to search (default: auto-detect)",
    )

    args = parser.parse_args()

    try:
        config = load_config(source_dirs=args.source_dirs)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    result = verify_candidate(args.name, args.file_path, config, verbose=args.verbose)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "DEAD" if result["is_dead"] else "ALIVE"
        if result["notebook_only"]:
            status = "NOTEBOOK-ONLY"

        print(f"Status: {status}")
        print(f"Name: {result['name']}")
        print(f"File: {result['file_path']}")

        if args.verbose:
            print("\nVerification steps:")
            for detail in result["verification_details"]:
                print(f"  - {detail}")

        if result["references"]:
            print(f"\nReferences found ({len(result['references'])}):")
            for ref in result["references"][:10]:
                print(f"  {ref}")
            if len(result["references"]) > 10:
                print(f"  ... and {len(result['references']) - 10} more")

        if result["notebook_references"]:
            print(f"\nNotebook references ({len(result['notebook_references'])}):")
            for ref in result["notebook_references"][:5]:
                print(f"  {ref}")
            if len(result["notebook_references"]) > 5:
                print(f"  ... and {len(result['notebook_references']) - 5} more")


if __name__ == "__main__":
    main()
