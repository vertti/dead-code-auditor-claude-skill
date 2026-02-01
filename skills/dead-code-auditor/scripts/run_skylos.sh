#!/bin/bash
# Run skylos with auto-detected or configured settings
#
# Usage: run_skylos.sh [confidence] [output-file] [source-dirs...]
#   confidence: Minimum confidence threshold (default: 60)
#   output-file: Path to write JSON output (default: stdout)
#   source-dirs: Optional explicit source directories (default: auto-detect)
#
# Example:
#   ./run_skylos.sh 80 /tmp/skylos.json
#   ./run_skylos.sh 60 /tmp/out.json src mypackage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find repo root
REPO_ROOT="$SCRIPT_DIR"
while [[ "$REPO_ROOT" != "/" ]]; do
    if [[ -f "$REPO_ROOT/pyproject.toml" ]] || [[ -f "$REPO_ROOT/setup.py" ]] || [[ -d "$REPO_ROOT/.git" ]]; then
        break
    fi
    REPO_ROOT="$(dirname "$REPO_ROOT")"
done

cd "$REPO_ROOT"

CONFIDENCE="${1:-60}"
OUTPUT_FILE="${2:-/dev/stdout}"
shift 2 2>/dev/null || true

# Get source directories from args or auto-detect
if [[ $# -gt 0 ]]; then
    SOURCE_DIRS="$*"
else
    SOURCE_DIRS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from config import load_config
config = load_config()
print(' '.join(config.source_dirs))
" 2>/dev/null || echo "")

    if [[ -z "$SOURCE_DIRS" ]]; then
        echo "Error: Could not auto-detect source directories" >&2
        exit 1
    fi
fi

# Get exclude folders from config
EXCLUDE_ARGS=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from config import load_config
config = load_config()
for d in config.exclude_dirs:
    if '*' not in d:  # skylos doesn't support glob patterns
        print(f'--exclude-folder {d}')
" 2>/dev/null | tr '\n' ' ' || echo "--exclude-folder tests --exclude-folder __pycache__")

echo "Running skylos with confidence=$CONFIDENCE" >&2
echo "Source dirs: $SOURCE_DIRS" >&2
echo "Output: $OUTPUT_FILE" >&2
echo "" >&2

# shellcheck disable=SC2086
uvx skylos $SOURCE_DIRS \
    --confidence "$CONFIDENCE" \
    $EXCLUDE_ARGS \
    --json \
    -o "$OUTPUT_FILE"
