#!/bin/sh
# Builds tu104_sim against Mesa
# Usage: tu104_sim_build.sh MESA_SRC MESA_BUILD [OUT]
set -e
MESA=$1
BUILD=$2
OUT=${3:-$(dirname "$0")/tu104_sim}
[ -n "$MESA" ] && [ -n "$BUILD" ] || { echo "usage: $0 MESA_SRC MESA_BUILD [OUT]" >&2; exit 1; }

cc -O1 -g -std=gnu11 -DUTIL_ARCH_LITTLE_ENDIAN=1 -DUTIL_ARCH_BIG_ENDIAN=0 -o "$OUT" \
	-I"$MESA/include" -I"$MESA/src" -I"$MESA/src/nouveau/mme" \
	-I"$MESA/src/nouveau/headers" -I"$MESA/src/nouveau/headers/nvidia/classes" \
	-I"$BUILD/src/nouveau/headers" -I"$BUILD/src" \
	"$(dirname "$0")/tu104_sim.c" \
	"$MESA/src/nouveau/mme/mme_tu104.c" \
	"$MESA/src/nouveau/mme/mme_tu104_sim.c"
