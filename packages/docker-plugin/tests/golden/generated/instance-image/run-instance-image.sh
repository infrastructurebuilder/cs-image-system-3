#!/usr/bin/env bash
# cs-image-system lifecycle runner: instance-image
# run id: 2026_08_26t12_00_00
# Deferred commands accumulated while generating this lifecycle,
# in phase order. Paths are relative to this lifecycle's directory.
# state: workspace tofu-docker -> local://state/tofu_docker.tfstate
# NOTE: builders' pre/post finalize hooks are NOT part of this
# script; a --no-dry-run run performs them in-process.
set -euo pipefail
cd "$(dirname "$0")"
CSIS_ROOT="$(cd "../.." && pwd)"   # the configuration root, relative to this script

# --- phase: image-generation ---
( cd "pckr-docker/image-generation/block-000" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && DOCKER_CONTEXT=csis-fixture-daemon /usr/local/bin/packer build . )

# --- phase: instance-generation ---
( cd "tofu-docker/instance-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && rm -f tfplan )
( cd "tofu-docker/instance-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && DOCKER_CONTEXT=csis-fixture-daemon /usr/local/bin/tofu init -input=false -reconfigure -backend-config=tofu-docker-instance-generation.tfbackend.hcl )
( cd "tofu-docker/instance-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && DOCKER_CONTEXT=csis-fixture-daemon /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "tofu-docker/instance-generation" && cd "$(cs-image-system materialize . --root-dir "$CSIS_ROOT")" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
