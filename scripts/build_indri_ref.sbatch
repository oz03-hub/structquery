#!/bin/bash
#SBATCH --job-name=indri_ref_build
#SBATCH --partition=cpu
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
# Builds the stock Indri command-line tools (IndriBuildIndex, IndriRunQuery, dumpindex)
# from the vendored source with Indri's own configure/make. These are only used as a
# reference for the parity tests; structquery itself is built by CMake (see CMakeLists.txt).
#
#   sbatch scripts/build_indri_ref.sbatch [WORK_DIR]
#
# WORK_DIR defaults to scratchspace/indripy. Output: $WORK_DIR/indri-ref/bin.
set -euo pipefail
REPO="${SLURM_SUBMIT_DIR:-$PWD}"
WORK="${1:-$REPO/scratchspace/indripy}"
JOBS="${SLURM_CPUS_PER_TASK:-1}"
echo "host=$(hostname) date=$(date) jobs=$JOBS"
module list 2>&1 || true
g++ --version | head -1

SRC="$WORK/build-ref"
PREFIX="$WORK/indri-ref"
rm -rf "$SRC"            # only ever this job's own scratch copy
mkdir -p "$SRC" "$PREFIX"
cp -r "$REPO/third_party/indri/." "$SRC/"
cd "$SRC"
# git does not keep the empty build directories that Indri's makefiles expect
mkdir -p obj depend contrib/antlr/obj contrib/lemur/obj contrib/xpdf/obj
./configure --prefix="$PREFIX" CXXFLAGS="-O2 -g0 -fPIC -std=gnu++11" CFLAGS="-O2 -fPIC"
grep -E '^(DEFS|CXXFLAGS|CPPFLAGS|LIBS|DEPENDENCIES|NEED_ANTLR)' MakeDefns Makefile.app || true
make -j "$JOBS"
make install
ls -la "$PREFIX/bin" "$PREFIX/lib"
echo "done $(date)"
