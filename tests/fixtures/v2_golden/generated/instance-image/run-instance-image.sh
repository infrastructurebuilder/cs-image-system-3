#!/usr/bin/env bash
# cs-image-system lifecycle runner: instance-image
# run id: 2026_08_26t12_00_00
# Deferred commands accumulated while generating this lifecycle,
# in phase order. Paths are relative to this lifecycle's directory.
# state: workspace open-tofu -> s3://noaa-ioos-cloud-sandbox-tfstate/statefiles/csia-image-system-test/open_tofu.tfstate
# state: workspace tofu-gce -> s3://noaa-ioos-cloud-sandbox-tfstate/statefiles/csia-image-system-test/tofu_gce.tfstate
# NOTE: builders' pre/post finalize hooks are NOT part of this
# script; a --no-dry-run run performs them in-process.
set -euo pipefail
cd "$(dirname "$0")"
CSIS_ROOT="$(cd "../.." && pwd)"   # the configuration root, relative to this script

# --- phase: image-generation ---
( cd "pckr-ebs-ans/image-generation/block-000" && /usr/local/bin/packer build . )
( cd "pckr-ebs-ans/image-generation/block-001" && /usr/local/bin/packer build . )
( cd "pckr-gce-ans/image-generation/block-000" && /usr/local/bin/packer build . )
( cd "some-other-builder/image-generation/block-000" && packer-1.9.4 build . )

# --- phase: instance-generation ---
( cd "open-tofu/instance-generation" && rm -f tfplan )
( cd "open-tofu/instance-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=open-tofu-instance-generation.tfbackend.hcl )
( cd "open-tofu/instance-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "open-tofu/instance-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
( cd "tofu-gce/instance-generation" && rm -f tfplan )
( cd "tofu-gce/instance-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=tofu-gce-instance-generation.tfbackend.hcl )
( cd "tofu-gce/instance-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "tofu-gce/instance-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
