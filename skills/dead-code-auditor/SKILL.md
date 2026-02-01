---
name: dead-code-auditor
description: Find dead code in Python ML projects using vulture and skylos, accounting for notebook usage
allowed-tools: Read, Bash, Grep, Glob, Write, Edit, Task
user-invocable: true
---

# Dead Code Auditor for Python ML Projects

Find dead code using vulture + skylos, then verify each candidate with intelligent agents.

## Workflow

### Step 1: Run Discovery

```bash
uv run python $SKILL_DIR/scripts/generate_report.py --limit 30
```

This runs vulture and skylos, merges results, and outputs a JSON file with candidates.

Options:
- `--limit N` - Limit to N candidates (recommended: start with 30-50)
- `--vulture-confidence N` - Min confidence for vulture (default: 60)
- `--skylos-confidence N` - Min confidence for skylos (default: 60)
- `--skip-skylos` - Use only vulture

### Step 2: Read Candidates

Read the JSON file output from step 1 to get the list of candidates.

### Step 3: Spawn Verification Agents

**CRITICAL**: Spawn parallel Explore agents to verify candidates. Group into batches of 5-10.

Use multiple Task tool calls in a single message:

```
Task(subagent_type="Explore", prompt="Verify candidates 1-10: ...")
Task(subagent_type="Explore", prompt="Verify candidates 11-20: ...")
Task(subagent_type="Explore", prompt="Verify candidates 21-30: ...")
```

#### Verification Agent Prompt

```
Verify if these code items are truly dead (unused) in the codebase.

For EACH candidate, check:
1. Is it called/referenced in source code? (use Grep)
2. Is it used in notebooks? (grep *.ipynb)
3. Is it accessed dynamically? (getattr, dict keys, string literals)
4. Is it exported in __init__.py or __all__?
5. Is it a protocol method or framework callback?
6. Is it a public API parameter (may be unused internally but needed for callers)?

Candidates:
{paste candidates here with file_path, line, name, type}

Respond with a table:
| name | file_path | verdict | reason |

Verdicts: DEAD | ALIVE | NOTEBOOK_ONLY

Be ACCURATE. When in doubt, mark as ALIVE.
```

#### What Makes Something ALIVE (Not Dead)

- **Called anywhere** in source (excluding tests)
- **Used in notebooks**
- **Dynamic access**: `getattr(obj, "name")`, `obj["name"]`, `"name"` in strings
- **Exported**: in `__init__.py` imports or `__all__`
- **Protocol methods**: `__enter__`, `__exit__`, `__iter__`, etc.
- **Framework callbacks**: Flyte tasks, pytest fixtures, Flask routes, Pydantic validators
- **Public parameters**: Function params exist for callers even if unused internally
- **Enum values**: Often accessed via `Enum.VALUE` or string matching
- **Dataclass/Pydantic fields**: Accessed via serialization

### Step 4: Generate Report

After agents complete, collect results into a markdown report:

```markdown
# Dead Code Audit Report

## Verified Dead Code (Safe to Remove)
| File | Line | Name | Type | Reason |

## Notebook-Only Code
| File | Line | Name | Type |

## False Positives (Kept)
| File | Line | Name | Reason |
```

## Configuration

Optional `.dead-code-auditor.json` in repo root:

```json
{
  "source_dirs": ["src", "mypackage"],
  "exclude_dirs": ["tests", "docs"],
  "extra_ignored_decorators": ["@my_decorator"],
  "extra_ignored_names": ["my_special_*"]
}
```

## Whitelist

Add false positives to `whitelist.py`:

```python
unused_func  # Used by Flyte @task
ClassName  # Plugin base class
```

## Tips

1. Start with `--limit 30` to test the workflow
2. Agents should READ the source file to understand context
3. Check class inheritance - methods may be called on parent
4. Check framework documentation for magic names
5. When in doubt, keep it - false negatives beat deleted live code
