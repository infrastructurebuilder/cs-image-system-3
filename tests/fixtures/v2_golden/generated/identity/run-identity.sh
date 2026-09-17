#!/usr/bin/env bash
# cs-image-system lifecycle runner: identity
# run id: 2026_08_26t12_00_00
# Deferred commands accumulated while generating this lifecycle,
# in phase order. Paths are relative to this lifecycle's directory.
# state: workspace oktagroups -> local://state/oktagroups.tfstate
# state: workspace okta-tf-users -> local://state/okta_tf_users.tfstate
# NOTE: builders' pre/post finalize hooks are NOT part of this
# script; a --no-dry-run run performs them in-process.
set -euo pipefail
cd "$(dirname "$0")"
CSIS_ROOT="$(cd "../.." && pwd)"   # the configuration root, relative to this script

# --- phase: group-generation ---
( cd "oktagroups/group-generation" && rm -f tfplan )
( cd "oktagroups/group-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=oktagroups-group-generation.tfbackend.hcl )
( cd "oktagroups/group-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "oktagroups/group-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
