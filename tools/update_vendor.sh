#!/usr/bin/env bash
# Refresh vendor/ from the local upstream pyqula working tree (read-only source).
# Usage: tools/update_vendor.sh [/path/to/pyqula]
set -euo pipefail
SRC="${1:-/path/to/pyqula}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DST="$HERE/vendor"
GUIDE="$SRC/documentation/user_guide.md"
if [ ! -f "$GUIDE" ]; then     # before writing anything: never a mixed copy
    echo "update_vendor.sh: $GUIDE is missing; the in-app help needs pyqula's guide" >&2
    exit 1
fi
mkdir -p "$DST"
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' "$SRC/src/pyqula/" "$DST/pyqula/"
cp "$GUIDE" "$DST/pyqula_user_guide.md"
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' --exclude='*.OUT' \
      --exclude='*.pkl' --exclude='*.png' --exclude='*.pdf' --exclude='*.npy' \
      "$SRC/examples/" "$DST/pyqula_examples/"
HEAD=$(git -C "$SRC" rev-parse HEAD)
DATE=$(git -C "$SRC" log -1 --format=%ci)
MOD=$(git -C "$SRC" status --short src | sed 's/^/    /')
DEPS=$(python3 - "$SRC/pyproject.toml" <<'PY'
import sys, tomllib
d = tomllib.load(open(sys.argv[1], "rb"))["project"]
for x in d["dependencies"]: print("    - " + x)
PY
)
cat > "$DST/VENDOR.md" <<EOT
# Vendored pyqula

This directory holds a **read-only local copy** of pyqula used by guiqula
during development. Never edit anything under \`vendor/pyqula/\`; refresh
the whole copy instead.

- Source: \`$SRC\` (working tree, not git HEAD)
- Upstream HEAD at copy time: \`$HEAD\` ($DATE)
- Copied on: $(date +%Y-%m-%d)
- Uncommitted upstream changes that were included in this copy:
${MOD:-    (none)}

Contents:
- \`pyqula/\` — the package (\`src/pyqula\` upstream), without \`__pycache__\`
- \`pyqula_user_guide.md\` — upstream \`documentation/user_guide.md\`
- \`pyqula_examples/\` — upstream \`examples/\` (scripts only, outputs stripped)

Upstream runtime dependencies at copy time (mirror them in guiqula's
\`pyproject.toml\`; optional extras are not listed):
$DEPS

Refresh with \`tools/update_vendor.sh\` (re-runs the same rsync and rewrites
this file). The upstream repository at the source path above must never be
modified from a guiqula session: no edits, no \`pip install -e\`, no running
scripts with the cwd inside it (pyqula writes \`.OUT\` files to the cwd).
EOT
echo "vendor refreshed from $SRC @ $HEAD"
# the in-app help (decision 13.13): every section a registry entry names must still exist,
# and every docstring must still be read from the source; fixes to the entries' guide=
# anchors that a renamed upstream section forces may join the refresh commit (CLAUDE.md)
cd "$HERE"
if ! python -m pytest -q tests/test_help.py tests/engine/test_help_docstrings.py; then
    echo "update_vendor.sh: the in-app help no longer matches the new pyqula (see above)" >&2
    exit 2
fi
