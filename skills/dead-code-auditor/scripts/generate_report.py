#!/usr/bin/env python3
"""Discover dead code candidates using vulture and skylos.

This script runs static analysis tools to find potential dead code,
merges and deduplicates results, then outputs JSON for agent verification.

Usage:
    generate_report.py [options]

Examples:
    generate_report.py
    generate_report.py --source-dirs src mypackage
    generate_report.py --vulture-confidence 80 --limit 50
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


def run_vulture(config: Config, min_confidence: int = 60) -> list[dict]:
    """Run vulture and parse its output."""
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
    exclude_args = []
    for d in config.exclude_dirs:
        if "*" not in d:
            exclude_args.extend(["--exclude-folder", d])

    cmd = [
        "uvx",
        "skylos",
        *config.source_dirs,
        "--confidence",
        str(confidence),
        *exclude_args,
        "--json",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=config.repo_root,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("Warning: skylos timed out", file=sys.stderr)
        return []

    if not result.stdout.strip():
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Warning: failed to parse skylos JSON output", file=sys.stderr)
        return []

    candidates = []
    unused_keys = [
        "unused_functions",
        "unused_classes",
        "unused_imports",
        "unused_variables",
        "unused_parameters",
    ]

    for key in unused_keys:
        items = data.get(key, [])
        if not isinstance(items, list):
            continue

        for item in items:
            item_confidence = item.get("confidence", 0)
            if item_confidence < confidence:
                continue

            name = item.get("simple_name") or item.get("name", "")
            file_path = item.get("file", "")

            if file_path.startswith(str(config.repo_root)):
                file_path = str(Path(file_path).relative_to(config.repo_root))

            candidates.append({
                "source": "skylos",
                "file_path": file_path,
                "line": item.get("line", 0),
                "name": name,
                "type": item.get("type", "unknown"),
                "confidence": item_confidence,
                "message": f"unused {item.get('type', 'item')} (0 references)",
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


def main():
    parser = argparse.ArgumentParser(description="Discover dead code candidates")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write output (default: scratchpad or /tmp)",
    )
    parser.add_argument(
        "--source-dirs",
        nargs="+",
        help="Source directories to analyze (default: auto-detect)",
    )
    parser.add_argument(
        "--vulture-confidence",
        type=int,
        default=60,
        help="Minimum vulture confidence threshold (default: 60)",
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
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of candidates to output (0 = no limit)",
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

    print("=" * 60)
    print("Dead Code Discovery")
    print("=" * 60)
    print(f"Repository: {config.repo_root}")
    print(f"Source dirs: {config.source_dirs}")
    print(f"Test dirs: {config.test_dirs}")
    print(f"Notebooks: {len(config.notebook_paths)}")
    print()

    # Load whitelist
    skill_dir = SCRIPT_DIR.parent
    whitelist = load_whitelist(skill_dir)
    print(f"Loaded {len(whitelist)} whitelist entries")

    # Run discovery tools
    print("\nRunning discovery tools...")
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
    print(f"Whitelisted (skipped): {whitelist_count}")

    # Apply limit if specified
    if args.limit > 0 and len(filtered_candidates) > args.limit:
        filtered_candidates = filtered_candidates[:args.limit]
        print(f"Limited to first {args.limit} candidates")

    # Output JSON
    candidates_file = output_dir / f"dead_code_candidates_{timestamp}.json"
    output_data = {
        "metadata": {
            "repo_root": str(config.repo_root),
            "source_dirs": config.source_dirs,
            "test_dirs": config.test_dirs,
            "notebook_count": len(config.notebook_paths),
            "total_candidates": len(filtered_candidates),
            "whitelist_count": whitelist_count,
            "vulture_confidence": args.vulture_confidence,
            "skylos_confidence": args.skylos_confidence,
            "timestamp": timestamp,
        },
        "candidates": filtered_candidates,
    }

    with open(candidates_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print("\n" + "=" * 60)
    print("Discovery Complete")
    print("=" * 60)
    print(f"Candidates file: {candidates_file}")
    print(f"Total candidates for verification: {len(filtered_candidates)}")


if __name__ == "__main__":
    main()
