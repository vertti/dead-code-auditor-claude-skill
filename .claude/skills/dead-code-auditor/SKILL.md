---
name: dead-code-auditor
description: Find dead code in Python ML projects using vulture and skylos, accounting for notebook usage
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
  - Write
  - Edit
user-invocable: true
---

# Dead Code Auditor for Python ML Projects

Find and report dead code in Python projects using vulture and skylos tools, with verification against Jupyter notebook usage.

## Key Principle

**Tool confidence scores are ONLY for initial discovery. Every item in the final report must be 100% verified dead via grep/ripgrep searches.**

Vulture and skylos find CANDIDATES, not confirmed dead code. The verification phase is critical.

## Quick Start

Run the full audit:

```bash
uv run python .claude/skills/dead-code-auditor/scripts/generate_report.py
```

Or with custom options:

```bash
uv run python .claude/skills/dead-code-auditor/scripts/generate_report.py \
    --source-dirs src mypackage \
    --vulture-confidence 100 \
    --output-dir /tmp
```

## How It Works

### Phase 1: Auto-Detection

The tool automatically detects:
- **Source directories**: Python packages (folders with `__init__.py`) at repo root
- **Notebooks**: All `.ipynb` files in the repository
- **Test directories**: `tests/`, `test/`, `*_tests/`, `tests_*/` patterns

### Phase 2: Discovery

Run vulture and skylos to generate initial candidates:

```bash
# Run vulture (auto-detects source dirs)
.claude/skills/dead-code-auditor/scripts/run_vulture.sh 80

# Run skylos
.claude/skills/dead-code-auditor/scripts/run_skylos.sh 60 /tmp/skylos_output.json
```

### Phase 3: Verification (CRITICAL)

For EACH candidate, verify it's truly dead:

```bash
uv run python .claude/skills/dead-code-auditor/scripts/verify_candidate.py <name> <file_path>
```

Verification checks:
1. Source code references (excluding tests)
2. Notebook references (all `.ipynb` files)
3. String literal references (dynamic dispatch)
4. `__init__.py` re-exports and `__all__` entries
5. Class inheritance patterns

### Phase 4: Generate Report

Only verified dead code (ZERO references found) is included in the report.

## Configuration

Create `.dead-code-auditor.json` in your repo root (optional):

```json
{
  "source_dirs": ["src", "mypackage"],
  "exclude_dirs": ["tests", "test", "docs", "examples"],
  "exclude_patterns": ["*_test.py", "conftest.py"],
  "extra_ignored_decorators": ["@my_custom_decorator"],
  "extra_ignored_names": ["my_special_*"]
}
```

If not provided, the tool auto-detects settings.

## Built-in Exclusions

### Directories (auto-excluded from analysis)
- `tests/`, `test/`, `*_tests/`, `tests_*/` - Test code
- `__pycache__`, `*.egg-info`, `build`, `dist`, `.git` - Build artifacts

### Decorators (ignored as framework-required)
- `@pytest.fixture`, `@pytest.mark.*`
- `@lru_cache`, `@cached_property`
- `@property`, `@staticmethod`, `@classmethod`
- `@abstractmethod`, `@overload`
- `@task`, `@workflow`, `@dynamic` (Flyte)
- `@app.route`, `@router.*` (web frameworks)

### Names (ignored patterns)
- `test_*`, `*_fixture`
- `setUp`, `tearDown`, `setUpClass`, `tearDownClass`
- `_*` (private by convention)

## Whitelist

### Built-in whitelist (`whitelist_builtin.py`)
Common false positives across Python ML projects.

### Project whitelist (`whitelist.py`)
Add project-specific false positives:

```python
# whitelist.py - vulture whitelist format
unused_func  # Used by Flyte @task decorator
ClassName  # Base class for plugin system
```

### Auto-generated whitelist
The tool can generate a project-specific whitelist by detecting:
- Flyte task/workflow functions
- CLI entry points from pyproject.toml
- Pybind11 bindings
- Plugin registrations

```bash
uv run python .claude/skills/dead-code-auditor/scripts/generate_whitelist.py
```

## Report Format

```markdown
# Dead Code Audit Report

## Executive Summary
| Category | Count |
|----------|-------|
| Verified dead code | X |
| Notebook-only code | Y |

## Verified Dead Code (Safe to Remove)
| File | Line | Name | Type |
|------|------|------|------|

## Notebook-Only Code
Code used in notebooks but not in source. Consider:
- Moving to source if generally useful
- Keeping if notebook-specific
- Inlining if one-off

## Verification Methodology
...
```

## Manual Verification

When verifying a candidate manually:

```bash
# Check source references
rg "NAME" src/ --type py -l

# Check notebook references
rg "NAME" --glob "*.ipynb"

# Check string literals (dynamic dispatch)
rg '"NAME"|'\''NAME'\''' src/

# Check re-exports
rg "NAME" --glob "__init__.py"
```

## After Running

1. Review the "Verified Dead Code" section
2. For each item, decide:
   - Remove (truly dead)
   - Add to whitelist (false positive)
   - Keep (has legitimate use not detected)
3. Test removal: `pytest` or `make test`
4. Update whitelist.py as needed
