#!/usr/bin/env bash
# cs-image-system lifecycle runner: storage
# run id: 2026_08_26t12_00_00
# Deferred commands accumulated while generating this lifecycle,
# in phase order. Paths are relative to this lifecycle's directory.
# state: workspace aws-ebs -> s3://my-east1-tfstate-bucket/statefiles/csia/aws_ebs.tfstate
# state: workspace aws-efs -> s3://my-east1-tfstate-bucket/statefiles/csia/aws_efs.tfstate
# state: workspace aws-s3 -> s3://my-east1-tfstate-bucket/statefiles/csia/aws_s3.tfstate
# state: workspace gcp-gcs -> s3://my-east1-tfstate-bucket/statefiles/csia/gcp_gcs.tfstate
# state: workspace gcp-pd -> s3://my-east1-tfstate-bucket/statefiles/csia/gcp_pd.tfstate
# NOTE: builders' pre/post finalize hooks are NOT part of this
# script; a --no-dry-run run performs them in-process.
set -euo pipefail
cd "$(dirname "$0")"
CSIS_ROOT="$(cd "../.." && pwd)"   # the configuration root, relative to this script

# --- phase: storage-generation ---
( cd "aws-ebs/storage-generation" && rm -f tfplan )
( cd "aws-ebs/storage-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=aws-ebs-storage-generation.tfbackend.hcl )
( cd "aws-ebs/storage-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "aws-ebs/storage-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
( cd "aws-efs/storage-generation" && rm -f tfplan )
( cd "aws-efs/storage-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=aws-efs-storage-generation.tfbackend.hcl )
( cd "aws-efs/storage-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "aws-efs/storage-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
( cd "aws-s3/storage-generation" && rm -f tfplan )
( cd "aws-s3/storage-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=aws-s3-storage-generation.tfbackend.hcl )
( cd "aws-s3/storage-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "aws-s3/storage-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
( cd "gcp-gcs/storage-generation" && rm -f tfplan )
( cd "gcp-gcs/storage-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=gcp-gcs-storage-generation.tfbackend.hcl )
( cd "gcp-gcs/storage-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "gcp-gcs/storage-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
( cd "gcp-pd/storage-generation" && rm -f tfplan )
( cd "gcp-pd/storage-generation" && /usr/local/bin/tofu init -input=false -reconfigure -backend-config=gcp-pd-storage-generation.tfbackend.hcl )
( cd "gcp-pd/storage-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )
( cd "gcp-pd/storage-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )
