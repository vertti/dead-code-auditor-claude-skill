# Dead Code Auditor - Claude Code Skill

A Claude Code skill that finds dead code in Python ML projects using [vulture](https://github.com/jendrikseipp/vulture) and [skylos](https://github.com/pyscaffold/skylos), with verification against Jupyter notebook usage.

## Why This Skill?

Static analysis tools like vulture flag many false positives, especially in ML projects where:
- Flyte/Airflow tasks are called by orchestration frameworks
- Functions are used in Jupyter notebooks but not imported in source
- CLI entry points are invoked externally
- Pybind11 bindings expose C++ code to Python

This skill **verifies every candidate** with grep/ripgrep searches before reporting, eliminating false positives.

## Features

- **Auto-detects** source directories, test directories, and notebooks
- **Verifies candidates** via grep/ripgrep (only reports 100% confirmed dead code)
- **Notebook-aware** - won't flag code used only in `.ipynb` files as dead
- **Built-in whitelist** for common ML patterns (pytest, Flyte, scikit-learn, PyTorch, etc.)
- **Auto-generates** project-specific whitelist (Flyte tasks, CLI entry points, pybind11 modules)
- **Configurable** via optional `.dead-code-auditor.json`

## Installation

Add to your project's `.claude/skills/` directory:

```bash
# Clone into your project
git clone https://github.com/vertti/dead-code-auditor-claude-skill.git /tmp/dca
cp -r /tmp/dca/.claude/skills/dead-code-auditor .claude/skills/
rm -rf /tmp/dca
```

Or add as a git submodule:

```bash
git submodule add https://github.com/vertti/dead-code-auditor-claude-skill.git .claude/skills/dead-code-auditor-repo
ln -s dead-code-auditor-repo/.claude/skills/dead-code-auditor .claude/skills/dead-code-auditor
```

## Usage

In Claude Code, use the skill:

```
/dead-code-auditor
```

Or run the scripts directly:

```bash
# Full audit with report
uv run python .claude/skills/dead-code-auditor/scripts/generate_report.py

# With custom options
uv run python .claude/skills/dead-code-auditor/scripts/generate_report.py \
    --source-dirs src mypackage \
    --vulture-confidence 100 \
    --output-dir ./reports

# Generate project-specific whitelist
uv run python .claude/skills/dead-code-auditor/scripts/generate_whitelist.py --append
```

## How It Works

### Phase 1: Discovery
Runs vulture and skylos to find **candidates** (not confirmed dead code).

### Phase 2: Verification
For each candidate, performs:
1. `rg "NAME" <source-dirs> --type py` - Source code references
2. `rg "NAME" --glob "*.ipynb"` - Notebook references
3. String literal search for dynamic dispatch patterns
4. `__init__.py` re-export checks
5. Class inheritance pattern checks

### Phase 3: Report
Only items with **zero references** are reported as dead code.

## Report Output

```markdown
# Dead Code Audit Report

## Executive Summary
| Category | Count |
|----------|-------|
| Verified dead code | 12 |
| Notebook-only code | 5 |
| Whitelisted (skipped) | 48 |
| Candidates checked | 156 |

## Verified Dead Code (Safe to Remove)
| File | Line | Name | Type |
|------|------|------|------|
| src/utils/legacy.py | 42 | old_function | function |
...

## Notebook-Only Code
Code used in notebooks but not in source...
```

## Configuration

Create `.dead-code-auditor.json` in your repo root (optional):

```json
{
  "source_dirs": ["src", "mypackage"],
  "exclude_dirs": ["tests", "docs", "examples"],
  "exclude_patterns": ["*_test.py", "conftest.py"],
  "extra_ignored_decorators": ["@my_custom_decorator"],
  "extra_ignored_names": ["my_special_*"]
}
```

Without config, the tool auto-detects:
- **Source dirs**: Packages with `__init__.py` at repo root or in `src/`
- **Test dirs**: `tests/`, `test/`, `*_tests/`, `tests_*/`
- **Notebooks**: All `*.ipynb` files

## Whitelists

### Built-in (`whitelist_builtin.py`)
Common patterns across Python ML projects:
- pytest fixtures and hooks
- Dataclass/Pydantic dunder methods
- scikit-learn API methods (`fit`, `transform`, `predict`)
- PyTorch Lightning hooks
- Click/Typer CLI patterns
- Flask/FastAPI route handlers

### Project-specific (`whitelist.py`)
Add your own false positives:

```python
my_function  # Called dynamically via plugin system
MyClass  # Base class - subclasses in external package
```

### Auto-generated
Detect and add project-specific patterns:

```bash
uv run python .claude/skills/dead-code-auditor/scripts/generate_whitelist.py --append
```

This finds:
- Flyte `@task` and `@workflow` functions
- CLI entry points from `pyproject.toml`
- Pybind11 module names (`.so` files)
- Abstract methods
- pytest fixtures

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (for running scripts)
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) for verification

Tools installed automatically via `uvx`:
- vulture
- skylos

## License

MIT License - see [LICENSE](LICENSE)
