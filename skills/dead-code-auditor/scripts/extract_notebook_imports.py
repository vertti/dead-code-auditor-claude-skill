#!/usr/bin/env python3
"""Extract all imports from Jupyter notebooks in the codebase.

This script parses .ipynb files and extracts:
- import statements (import X, import X as Y)
- from imports (from X import Y, from X import Y as Z)
- %run magic commands that source other files

Output: JSON with all imported module paths and names.

Usage:
    extract_notebook_imports.py [--output FILE]
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# Add script directory to path for config import
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import load_config


def extract_imports_from_code(code: str) -> set[str]:
    """Extract import names from Python code string."""
    imports = set()

    # Handle %run magic commands
    run_pattern = re.compile(r"^\s*%run\s+(?:-i\s+)?['\"]?([^'\"$\s]+)", re.MULTILINE)
    for match in run_pattern.finditer(code):
        imports.add(f"__run__:{match.group(1)}")

    # Remove magic commands and shell commands for AST parsing
    clean_lines = []
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("%") or stripped.startswith("!"):
            clean_lines.append("")  # Keep line numbers aligned
        else:
            clean_lines.append(line)
    clean_code = "\n".join(clean_lines)

    try:
        tree = ast.parse(clean_code)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                parts = alias.name.split(".")
                for i in range(len(parts)):
                    imports.add(".".join(parts[: i + 1]))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
                parts = node.module.split(".")
                for i in range(len(parts)):
                    imports.add(".".join(parts[: i + 1]))
            for alias in node.names:
                if node.module:
                    imports.add(f"{node.module}.{alias.name}")
                else:
                    imports.add(alias.name)

    return imports


def extract_names_from_code(code: str) -> set[str]:
    """Extract all referenced names from Python code (function calls, attribute access)."""
    names = set()

    clean_lines = []
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("%") or stripped.startswith("!"):
            clean_lines.append("")
        else:
            clean_lines.append(line)
    clean_code = "\n".join(clean_lines)

    try:
        tree = ast.parse(clean_code)
    except SyntaxError:
        return names

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)

    return names


def process_notebook(notebook_path: Path) -> dict:
    """Process a single notebook and extract imports and names."""
    try:
        with open(notebook_path, encoding="utf-8") as f:
            nb = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"error": str(e), "imports": [], "names": []}

    imports = set()
    names = set()

    cells = nb.get("cells", [])
    for cell in cells:
        if cell.get("cell_type") == "code":
            source = cell.get("source", [])
            if isinstance(source, list):
                code = "".join(source)
            else:
                code = source

            imports.update(extract_imports_from_code(code))
            names.update(extract_names_from_code(code))

    return {
        "imports": sorted(imports),
        "names": sorted(names),
    }


def main():
    parser = argparse.ArgumentParser(description="Extract imports from Jupyter notebooks")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    args = parser.parse_args()

    try:
        config = load_config()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    all_imports = set()
    all_names = set()
    notebook_details = {}

    for nb_path in config.notebook_paths:
        rel_path = str(nb_path.relative_to(config.repo_root))
        result = process_notebook(nb_path)
        notebook_details[rel_path] = result
        all_imports.update(result.get("imports", []))
        all_names.update(result.get("names", []))

    output = {
        "total_notebooks": len(config.notebook_paths),
        "all_imports": sorted(all_imports),
        "all_names": sorted(all_names),
        "notebooks": notebook_details,
    }

    output_str = json.dumps(output, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_str)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output_str)


if __name__ == "__main__":
    main()
