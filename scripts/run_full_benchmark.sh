#!/bin/bash
# Run the full benchmark across all providers, codecs, verticals, and VMAF targets.
# Each batch is a single (provider, codec, vertical, target) combination so
# parallelism stays under cloud-provider rate limits (~5-7 concurrent jobs).
#
# Usage (from repo root):
#     ./scripts/run_full_benchmark.sh
#
# To resume after interruption: comment out completed batches.

set -u

PROVIDERS=(mediaconvert bitmovin zencoder)
CODECS=(h265 av1)
VERTICALS=(ecommerce ugc archive security)
TARGETS=(85 89 93)

for provider in "${PROVIDERS[@]}"; do
    for codec in "${CODECS[@]}"; do
        if [[ "$provider" == "zencoder" && "$codec" == "av1" ]]; then
            continue
        fi
        for vertical in "${VERTICALS[@]}"; do
            for vmaf in "${TARGETS[@]}"; do
                echo
                echo "=== $provider $codec $vertical vmaf=$vmaf ==="
                .venv/bin/python -m benchmark.encode \
                    --provider "$provider" \
                    --codec "$codec" \
                    --vertical "$vertical" \
                    --vmaf "$vmaf" \
                    --vmaf-threads 8
            done
        done
    done
done
