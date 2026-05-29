#!/bin/bash
set -u
ALGOS="afg-b-l8 afg-f-l8 afg-m-l8 ptg-b-l7 ptg-f-l2 ptg-m-l1 vrs-f-l6 vrs-m-l5"
DATES="20260326 20260327 20260329 20260330 20260331 20260401 20260402 20260403 20260405 20260406"
for algo in $ALGOS; do
  echo ""
  echo "======================================================"
  echo "  Starting OOS for: $algo  ($(date))"
  echo "======================================================"
  for d in $DATES; do
    rm -rf "execution_algos/${algo}/results/${d}"
    rm -rf "execution_algos/simple_execution_strategy/results/${d}"
  done
  uv run python3 scripts/run_oos_eval.py --algo "$algo" 2>&1 | tee "oos-results/${algo}-run.log"
  echo "  Done: $algo  ($(date))"
done
echo ""
echo "ALL CONTEXT ALGOS DONE."
