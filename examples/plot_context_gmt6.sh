#!/usr/bin/env bash
# Requires GMT 6 + GSHHG + Ghostscript. Not a reviewed publication map.
# No political boundaries; no remote DEM download. Run from any directory.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v gmt >/dev/null || { echo 'GMT 6 is required' >&2; exit 1; }
case "$(gmt --version)" in 6.*) ;; *) echo 'This example requires GMT 6' >&2; exit 1 ;; esac
mkdir -p "$ROOT/outputs"
cd "$ROOT/outputs"
FAULTS="$ROOT/data/derived/gem_faults_east_asia_bbox.gmt"
if [[ -f "$ROOT/data/local/gmt-china/CN-faults.gmt" ]]; then
    FAULTS="$ROOT/data/local/gmt-china/CN-faults.gmt"
    echo 'Fault layer: local CAFDv2023 community conversion (check terms)' >&2
else
    echo 'Fault layer: GEM regional subset (not CAFD)' >&2
fi
gmt begin regional_context png
    gmt basemap -R70/140/0/60 -JM18c -Baf
    gmt coast -Dl -A5000 -Ggray95 -Slightblue -W0.25p,gray50
    gmt plot "$ROOT/data/derived/PB2002_boundaries.gmt" -W0.7p,blue
    gmt plot "$FAULTS" -W0.3p,firebrick
    if [[ -f "$ROOT/data/local/gmt-china/CN-block-L1.gmt" &&
          -f "$ROOT/data/local/gmt-china/CN-block-L1-deduced.gmt" &&
          -f "$ROOT/data/local/gmt-china/CN-block-L2.gmt" ]]; then
        gmt plot "$ROOT/data/local/gmt-china/CN-block-L2.gmt" -W0.7p,orange
        gmt plot "$ROOT/data/local/gmt-china/CN-block-L1-deduced.gmt" -W1p,purple,-
        gmt plot "$ROOT/data/local/gmt-china/CN-block-L1.gmt" -W1p,purple
    fi
    # Points only: Chinese text rendering depends on the local GMT/font setup.
    gmt plot "$ROOT/data/derived/cities_china_34_labels.gmt" -i0,1 -Sc0.09c -Gblack
    gmt legend -DjBL+w6c+o0.2c -F+gwhite+p0.3p <<'EOF'
S 0.3c - 0.6c - 0.7p,blue 1c PB2002 plate boundary
S 0.3c - 0.6c - 0.3p,firebrick 1c Faults (source printed in log)
S 0.3c c 0.09c black - 1c Natural Earth city points
EOF
gmt end
printf 'Created %s/outputs/regional_context.png\n' "$ROOT"
