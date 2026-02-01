#!/bin/bash
# Run vulture with auto-detected or configured settings
#
# Usage: run_vulture.sh [min-confidence] [source-dirs...]
#   min-confidence: Minimum confidence threshold (default: 80)
#   source-dirs: Optional explicit source directories (default: auto-detect)
#
# Example:
#   ./run_vulture.sh 100              # High confidence, auto-detect dirs
#   ./run_vulture.sh 80 src mypackage # Custom source directories

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Find repo root
REPO_ROOT="$SCRIPT_DIR"
while [[ "$REPO_ROOT" != "/" ]]; do
    if [[ -f "$REPO_ROOT/pyproject.toml" ]] || [[ -f "$REPO_ROOT/setup.py" ]] || [[ -d "$REPO_ROOT/.git" ]]; then
        break
    fi
    REPO_ROOT="$(dirname "$REPO_ROOT")"
done

cd "$REPO_ROOT"

MIN_CONFIDENCE="${1:-80}"
shift 2>/dev/null || true

# Get source directories from args or auto-detect
if [[ $# -gt 0 ]]; then
    SOURCE_DIRS="$*"
else
    # Auto-detect using Python config module
    SOURCE_DIRS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from config import load_config
config = load_config()
print(' '.join(config.source_dirs))
" 2>/dev/null || echo "")

    if [[ -z "$SOURCE_DIRS" ]]; then
        echo "Error: Could not auto-detect source directories" >&2
        echo "Specify them explicitly: $0 $MIN_CONFIDENCE src mypackage" >&2
        exit 1
    fi
fi

# Get exclusions and ignores from config
EXCLUDES=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from config import load_config, get_vulture_exclude_string
config = load_config()
print(get_vulture_exclude_string(config))
" 2>/dev/null || echo "tests,test,__pycache__,build,dist,.git")

IGNORE_DECORATORS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from config import load_config, get_vulture_ignore_decorators_string
config = load_config()
print(get_vulture_ignore_decorators_string(config))
" 2>/dev/null || echo "@pytest.fixture,@pytest.mark.*,@lru_cache,@property,@staticmethod,@classmethod,@abstractmethod,@overload,@task,@workflow,@dynamic")

IGNORE_NAMES=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from config import load_config, get_vulture_ignore_names_string
config = load_config()
print(get_vulture_ignore_names_string(config))
" 2>/dev/null || echo "test_*,*_fixture,setUp,tearDown,_*")

# Check for whitelists
WHITELIST_ARGS=""
BUILTIN_WHITELIST="$SKILL_DIR/whitelist_builtin.py"
PROJECT_WHITELIST="$SKILL_DIR/whitelist.py"

if [[ -f "$BUILTIN_WHITELIST" ]] && grep -q "^[^#]" "$BUILTIN_WHITELIST" 2>/dev/null; then
    WHITELIST_ARGS="$BUILTIN_WHITELIST"
fi
if [[ -f "$PROJECT_WHITELIST" ]] && grep -q "^[^#]" "$PROJECT_WHITELIST" 2>/dev/null; then
    WHITELIST_ARGS="$WHITELIST_ARGS $PROJECT_WHITELIST"
fi

echo "Running vulture with min-confidence=$MIN_CONFIDENCE" >&2
echo "Source dirs: $SOURCE_DIRS" >&2
echo "Excludes: $EXCLUDES" >&2
echo "" >&2

# shellcheck disable=SC2086
uvx vulture $SOURCE_DIRS \
    --min-confidence "$MIN_CONFIDENCE" \
    --exclude "$EXCLUDES" \
    --ignore-decorators "$IGNORE_DECORATORS" \
    --ignore-names "$IGNORE_NAMES" \
    --sort-by-size \
    $WHITELIST_ARGS
