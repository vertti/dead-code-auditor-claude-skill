#!/usr/bin/env python3
"""Generate a dead code audit report.

This script orchestrates the full dead code audit workflow:
1. Auto-detect project structure (or use config)
2. Run vulture and skylos to discover candidates
3. Verify each candidate with grep/ripgrep searches
4. Generate a markdown report

Usage:
    generate_report.py [options]

Examples:
    generate_report.py
    generate_report.py --source-dirs src mypackage
    generate_report.py --vulture-confidence 100 --output-dir /tmp
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add script directory to path for config import
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import Config, load_config
from verify_candidate import verify_candidate


def run_vulture(config: Config, min_confidence: int = 80) -> list[dict]:
    """Run vulture and parse its output."""
    source_dirs = " ".join(config.source_dirs)
    excludes = ",".join(config.exclude_dirs)
    decorators = ",".join(config.ignored_decorators)
    names = ",".join(config.ignored_names)

    # Check for whitelists
    skill_dir = SCRIPT_DIR.parent
    whitelist_args = []
    for wl in ["whitelist_builtin.py", "whitelist.py"]:
        wl_path = skill_dir / wl
        if wl_path.exists():
            try:
                content = wl_path.read_text()
                if any(line.strip() and not line.strip().startswith("#") for line in content.split("\n")):
                    whitelist_args.append(str(wl_path))
            except OSError:
                pass

    # Whitelist files must be passed as paths alongside source dirs
    cmd = [
        "uvx",
        "vulture",
        *config.source_dirs,
        *whitelist_args,
        "--min-confidence",
        str(min_confidence),
        "--exclude",
        excludes,
        "--ignore-decorators",
        decorators,
        "--ignore-names",
        names,
        "--sort-by-size",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=config.repo_root,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("Warning: vulture timed out", file=sys.stderr)
        return []

    candidates = []
    # Pattern handles optional ", N line(s)" suffix from --sort-by-size
    pattern = re.compile(r"^(.+):(\d+): (.+) \((\d+)% confidence(?:, \d+ lines?)?\)$")

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        match = pattern.match(line)
        if match:
            file_path, line_num, message, confidence = match.groups()

            name_match = re.search(r"unused (\w+) '([^']+)'", message)
            if name_match:
                item_type, name = name_match.groups()
            else:
                item_type = "unknown"
                name = message

            candidates.append({
                "source": "vulture",
                "file_path": file_path,
                "line": int(line_num),
                "name": name,
                "type": item_type,
                "confidence": int(confidence),
                "message": message,
            })

    return candidates


def run_skylos(config: Config, confidence: int = 60) -> list[dict]:
    """Run skylos and parse its JSON output."""
    output_file = Path("/tmp/skylos_output.json")

    exclude_args = []
    for d in config.exclude_dirs:
        if "*" not in d:  # skylos doesn't support glob patterns
            exclude_args.extend(["--exclude-folder", d])

    cmd = [
        "uvx",
        "skylos",
        *config.source_dirs,
        "--confidence",
        str(confidence),
        *exclude_args,
        "--json",
        "-o",
        str(output_file),
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=config.repo_root,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("Warning: skylos timed out", file=sys.stderr)
        return []

    if not output_file.exists():
        return []

    try:
        with open(output_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    candidates = []
    if isinstance(data, list):
        for item in data:
            candidates.append({
                "source": "skylos",
                "file_path": item.get("file", item.get("path", "")),
                "line": item.get("line", 0),
                "name": item.get("name", ""),
                "type": item.get("type", "unknown"),
                "confidence": item.get("confidence", 0),
                "message": item.get("message", ""),
            })
    elif isinstance(data, dict):
        for file_path, items in data.items():
            if isinstance(items, list):
                for item in items:
                    candidates.append({
                        "source": "skylos",
                        "file_path": file_path,
                        "line": item.get("line", 0),
                        "name": item.get("name", ""),
                        "type": item.get("type", "unknown"),
                        "confidence": item.get("confidence", 0),
                        "message": item.get("message", ""),
                    })

    return candidates


def load_whitelist(skill_dir: Path) -> set[str]:
    """Load the whitelist of known false positives."""
    names = set()

    for wl in ["whitelist_builtin.py", "whitelist.py"]:
        wl_path = skill_dir / wl
        if wl_path.exists():
            try:
                with open(wl_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            name = line.split()[0] if line.split() else ""
                            if name:
                                names.add(name)
            except OSError:
                pass

    return names


def generate_report(
    verified_dead: list[dict],
    notebook_only: list[dict],
    total_candidates: int,
    whitelist_count: int,
    config: Config,
    output_path: Path,
) -> None:
    """Generate the markdown report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report_lines = [
        "# Dead Code Audit Report",
        f"Generated: {timestamp}",
        "",
        "## Project Info",
        f"- **Repository**: {config.repo_root.name}",
        f"- **Source directories**: {', '.join(config.source_dirs)}",
        f"- **Notebooks found**: {len(config.notebook_paths)}",
        "",
        "## Executive Summary",
        "",
        "| Category | Count |",
        "|----------|-------|",
        f"| Verified dead code | {len(verified_dead)} |",
        f"| Notebook-only code | {len(notebook_only)} |",
        f"| Whitelisted (skipped) | {whitelist_count} |",
        f"| Candidates checked | {total_candidates} |",
        "",
    ]

    # Verified Dead Code section
    report_lines.extend([
        "## Verified Dead Code (Safe to Remove)",
        "",
        "Each item below has been verified with grep/ripgrep searches. ZERO references exist outside tests/.",
        "",
    ])

    if verified_dead:
        report_lines.extend([
            "| File | Line | Name | Type |",
            "|------|------|------|------|",
        ])
        for item in sorted(verified_dead, key=lambda x: (x["file_path"], x["line"])):
            report_lines.append(
                f"| {item['file_path']} | {item['line']} | `{item['name']}` | {item['type']} |"
            )
        report_lines.append("")
    else:
        report_lines.extend(["*No verified dead code found.*", ""])

    # Notebook-Only Code section
    report_lines.extend([
        "## Notebook-Only Code",
        "",
        "Code not used in source but IS used in notebooks. Consider:",
        "- Moving to source if generally useful",
        "- Keeping as-is if notebook-specific",
        "- Inlining into the notebook if one-off",
        "",
    ])

    if notebook_only:
        report_lines.extend([
            "| File | Line | Name | Type |",
            "|------|------|------|------|",
        ])
        for item in sorted(notebook_only, key=lambda x: (x["file_path"], x["line"])):
            report_lines.append(
                f"| {item['file_path']} | {item['line']} | `{item['name']}` | {item['type']} |"
            )
        report_lines.append("")
    else:
        report_lines.extend(["*No notebook-only code found.*", ""])

    # Verification Methodology section
    report_lines.extend([
        "## Verification Methodology",
        "",
        "For each candidate from vulture/skylos, these checks were performed:",
        "",
        "1. `rg \"NAME\" <source-dirs> --type py` - Any reference in source code",
        "2. `rg \"NAME\" --glob \"*.ipynb\"` - Notebook references",
        '3. `rg \'"NAME"|\'NAME\'\' <source-dirs>` - String literal references (dynamic dispatch)',
        "4. Check `__init__.py` files for re-exports and `__all__` entries",
        "5. Check for class inheritance patterns (for class names)",
        "",
        "A candidate is only marked as dead if ALL checks return zero results.",
        "",
    ])

    # Whitelist section
    report_lines.extend([
        "## Adding to Whitelist",
        "",
        "For false positives, add to `.claude/skills/dead-code-auditor/whitelist.py`:",
        "",
        "```python",
        "unused_func  # Reason why this appears unused but is needed",
        "ClassName  # Base class for plugin system",
        "```",
        "",
    ])

    # Write report
    with open(output_path, "w") as f:
        f.write("\n".join(report_lines))

    print(f"Report written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate dead code audit report")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write report (default: scratchpad or /tmp)",
    )
    parser.add_argument(
        "--source-dirs",
        nargs="+",
        help="Source directories to analyze (default: auto-detect)",
    )
    parser.add_argument(
        "--vulture-confidence",
        type=int,
        default=80,
        help="Minimum vulture confidence threshold (default: 80)",
    )
    parser.add_argument(
        "--skylos-confidence",
        type=int,
        default=60,
        help="Minimum skylos confidence threshold (default: 60)",
    )
    parser.add_argument(
        "--skip-skylos",
        action="store_true",
        help="Skip running skylos (use only vulture)",
    )

    args = parser.parse_args()

    try:
        config = load_config(source_dirs=args.source_dirs)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        scratchpad = os.environ.get("CLAUDE_SCRATCHPAD_DIR", "/tmp")
        output_dir = Path(scratchpad)

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"dead_code_report_{timestamp}.md"

    print("=" * 60)
    print("Dead Code Audit")
    print("=" * 60)
    print(f"Repository: {config.repo_root}")
    print(f"Source dirs: {config.source_dirs}")
    print(f"Test dirs: {config.test_dirs}")
    print(f"Notebooks: {len(config.notebook_paths)}")
    print(f"Output: {output_path}")
    print()

    # Load whitelist
    skill_dir = SCRIPT_DIR.parent
    whitelist = load_whitelist(skill_dir)
    print(f"Loaded {len(whitelist)} whitelist entries")

    # Run discovery tools
    print("\nPhase 1: Discovery")
    print("-" * 40)

    print(f"Running vulture (confidence >= {args.vulture_confidence})...")
    vulture_candidates = run_vulture(config, args.vulture_confidence)
    print(f"  Found {len(vulture_candidates)} candidates")

    skylos_candidates = []
    if not args.skip_skylos:
        print(f"Running skylos (confidence >= {args.skylos_confidence})...")
        skylos_candidates = run_skylos(config, args.skylos_confidence)
        print(f"  Found {len(skylos_candidates)} candidates")

    # Combine and deduplicate
    all_candidates = vulture_candidates + skylos_candidates
    seen = set()
    unique_candidates = []
    for c in all_candidates:
        key = (c["file_path"], c["name"])
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    print(f"\nTotal unique candidates: {len(unique_candidates)}")

    # Filter out whitelisted
    filtered_candidates = []
    whitelist_count = 0
    for c in unique_candidates:
        if c["name"] in whitelist:
            whitelist_count += 1
        else:
            filtered_candidates.append(c)

    print(f"After whitelist filtering: {len(filtered_candidates)} candidates")

    # Verify each candidate
    print("\nPhase 2: Verification")
    print("-" * 40)

    verified_dead = []
    notebook_only = []

    for i, candidate in enumerate(filtered_candidates, 1):
        name = candidate["name"]
        file_path = candidate["file_path"]
        print(f"  [{i}/{len(filtered_candidates)}] Verifying {name}...", end=" ", flush=True)

        result = verify_candidate(name, file_path, config)

        if result["is_dead"]:
            if result["notebook_only"]:
                notebook_only.append({**candidate, **result})
                print("NOTEBOOK-ONLY")
            else:
                verified_dead.append({**candidate, **result})
                print("DEAD")
        else:
            print("alive")

    # Generate report
    print("\nPhase 3: Report Generation")
    print("-" * 40)

    generate_report(
        verified_dead=verified_dead,
        notebook_only=notebook_only,
        total_candidates=len(filtered_candidates),
        whitelist_count=whitelist_count,
        config=config,
        output_path=output_path,
    )

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Verified dead code: {len(verified_dead)}")
    print(f"  Notebook-only code: {len(notebook_only)}")
    print(f"  Whitelisted: {whitelist_count}")
    print(f"  Checked: {len(filtered_candidates)}")
    print(f"\nReport: {output_path}")


if __name__ == "__main__":
    main()
