#!/bin/bash
#SBATCH --job-name=structquery_bcp
#SBATCH --partition=cpu
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
# Index BrowseComp-Plus with structquery and evaluate bag-of-words queries.
#   sbatch scripts/browsecompplus.sbatch            # full corpus (100,195 docs)
#   sbatch scripts/browsecompplus.sbatch 2000       # smoke test on the first 2000 docs
set -euo pipefail
REPO="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$REPO"
LIMIT="${1:-}"
echo "host=$(hostname) date=$(date) cpus=${SLURM_CPUS_PER_TASK:-1} limit=${LIMIT:-none}"
module list 2>&1 || true
source .venv/bin/activate
which python && python --version
export PYTHONPATH="$REPO/src"
NAME="browsecompplus${LIMIT:+-first$LIMIT}"
python -u examples/browsecompplus_eval.py \
  --data scratchspace/data/browsecompplus \
  --index "scratchspace/indripy/indexes/$NAME" \
  --out "scratchspace/indripy/runs/$NAME" \
  --workers "${SLURM_CPUS_PER_TASK:-1}" ${LIMIT:+--limit "$LIMIT"}
du -sh "scratchspace/indripy/indexes/$NAME"
echo "done $(date)"
