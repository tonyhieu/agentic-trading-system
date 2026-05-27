#!/bin/bash
set -u
ALGOS="afg-isl-g3l2 ptg-isl-g4l1"
DATES="20260326 20260327 20260329 20260330 20260331 20260401 20260402 20260403 20260405 20260406"
for algo in $ALGOS; do
  echo ""
  echo "  Starting OOS for: $algo  ($(date))"
  for d in $DATES; do
    rm -rf "execution_algos/${algo}/results/${d}"
    rm -rf "execution_algos/simple_execution_strategy/results/${d}"
  done
  uv run python3 scripts/run_oos_eval.py --algo "$algo" 2>&1 | tee "oos-results/${algo}-run.log"
  echo "  Done: $algo  ($(date))"
done
echo "ALL ISLAND ALGOS DONE."
