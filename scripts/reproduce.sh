#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$ROOT/src"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$ROOT/results"
if [ "$#" -gt 1 ]; then
  echo "usage: sh scripts/reproduce.sh [events|boundary-low|boundary-cap|boundary-check-low|boundary-check-cap|boundaries|sources|all]" >&2
  exit 2
fi
STAGE=${1:-all}
case "$STAGE" in
  events|boundary-low|boundary-cap|boundary-check-low|boundary-check-cap|boundaries|sources|all) ;;
  *) echo "unknown stage: $STAGE" >&2; exit 2 ;;
esac
if [ "$STAGE" = events ] || [ "$STAGE" = all ]; then
  python -m rivet.experiments \
    "$ROOT/data/public_windows.json" \
    "$ROOT/results" \
    --replayer "$ROOT/replayer/replay.py" \
    --ledger "$ROOT/data/canonical_ledgers.csv" \
    --expected "$ROOT/data/canonical_expected.json"
fi
if [ "$STAGE" = boundary-low ] || [ "$STAGE" = all ]; then
  python -m rivet.alias_case_generation "$ROOT" 1 2 3 4 5 6
fi
if [ "$STAGE" = boundary-cap ] || [ "$STAGE" = all ]; then
  python -m rivet.alias_case_generation "$ROOT" 7
fi
if [ "$STAGE" = boundary-check-low ] || [ "$STAGE" = all ]; then
  python -m rivet.alias_oracle_stage "$ROOT" low
fi
if [ "$STAGE" = boundary-check-cap ] || [ "$STAGE" = all ]; then
  python -m rivet.alias_oracle_stage "$ROOT" cap
fi
if [ "$STAGE" = boundaries ] || [ "$STAGE" = all ]; then
  python -m rivet.boundary_experiments "$ROOT"
fi
if [ "$STAGE" = sources ] || [ "$STAGE" = all ]; then
  python -m rivet.public_patch_experiments "$ROOT"
fi
if [ "$STAGE" = all ]; then
  sh "$ROOT/scripts/check.sh"
fi
