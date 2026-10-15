#!/usr/bin/env bash
# Refresh vendor/ from a local checkout of upstream pyqula (read-only source,
# https://github.com/joselado/pyqula), given as the argument or $PYQULA_SRC.
# Usage: tools/update_vendor.sh [/path/to/pyqula]
set -euo pipefail
SRC="${1:-${PYQULA_SRC:-}}"
if [ -z "$SRC" ]; then
    echo "usage: tools/update_vendor.sh /path/to/pyqula (or set PYQULA_SRC)" >&2
    exit 1
fi
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DST="$HERE/vendor"
# the guide: a MkDocs website since October 2026 (documentation/guide/ in the order of
# mkdocs.yml), assembled into one Markdown file by tools/assemble_guide.py; before, one file
GUIDE="$SRC/documentation/user_guide.md"
ASSEMBLED="$(mktemp)"
trap 'rm -f "$ASSEMBLED"' EXIT
if [ -f "$SRC/mkdocs.yml" ]; then      # before writing anything: never a mixed copy
    python3 "$HERE/tools/assemble_guide.py" "$SRC" "$ASSEMBLED"
elif [ -f "$GUIDE" ]; then
    cp "$GUIDE" "$ASSEMBLED"
else
    echo "update_vendor.sh: neither $SRC/mkdocs.yml nor $GUIDE is there; the in-app help" \
         "needs pyqula's guide" >&2
    exit 1
fi
mkdir -p "$DST"
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' "$SRC/src/pyqula/" "$DST/pyqula/"
cp "$ASSEMBLED" "$DST/pyqula_user_guide.md"
# only the package and the guide (the in-app help): upstream's examples stay upstream
HEAD=$(git -C "$SRC" rev-parse HEAD)
# the upstream repository's public URL, never the local path (the repository is public)
ORIGIN=$(git -C "$SRC" remote get-url origin 2>/dev/null \
         | sed -e 's#^git@github.com:#https://github.com/#' -e 's#\.git$##' || true)
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

- Source: a local checkout of ${ORIGIN:-upstream pyqula} (working tree, not git HEAD)
- Upstream HEAD at copy time: \`$HEAD\` ($DATE)
- Copied on: $(date +%Y-%m-%d)
- Uncommitted upstream changes that were included in this copy:
${MOD:-    (none)}

Contents:
- \`pyqula/\` — the package (\`src/pyqula\` upstream), without \`__pycache__\`
- \`pyqula_user_guide.md\` — upstream's user guide, the pages of \`documentation/guide/\` in the order of \`mkdocs.yml\` joined by \`tools/assemble_guide.py\` (the in-app help)

Upstream runtime dependencies at copy time (mirror them in guiqula's
\`pyproject.toml\`; optional extras are not listed):
$DEPS

Refresh with \`tools/update_vendor.sh\` (re-runs the same rsync and rewrites
this file). The upstream checkout it is copied from must never be
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
