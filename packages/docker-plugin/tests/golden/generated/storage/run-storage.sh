#!/usr/bin/env bash
# cs-image-system lifecycle runner: storage
# run id: 2026_08_26t12_00_00
# Deferred commands accumulated while generating this lifecycle,
# in phase order. Paths are relative to this lifecycle's directory.
# state: workspace docker-volume -> local://state/docker_volume.tfstate
# NOTE: builders' pre/post finalize hooks are NOT part of this
# script; a --no-dry-run run performs them in-process.
set -euo pipefail
cd "$(dirname "$0")"
CSIS_ROOT="$(cd "../.." && pwd)"   # the configuration root, relative to this script

# --- phase: storage-generation ---
( cd "docker-volume/storage-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && rm -f tfplan )
( cd "docker-volume/storage-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && DOCKER_CONTEXT=csis-fixture-daemon /usr/local/bin/tofu init -input=false -reconfigure -backend-config=docker-volume-storage-generation.tfbackend.hcl )
( cd "docker-volume/storage-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && DOCKER_CONTEXT=csis-fixture-daemon /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "docker-volume/storage-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
