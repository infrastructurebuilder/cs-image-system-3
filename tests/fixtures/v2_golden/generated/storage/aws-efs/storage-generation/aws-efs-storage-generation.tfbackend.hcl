# Backend 's3-east2' (s3) partial configuration for workspace aws-efs
bucket = "noaa-ioos-cloud-sandbox-tfstate"
key = "statefiles/csia-image-system-test/aws_efs.tfstate"
region = "us-east-2"
encrypt = true
use_lockfile = true
profile = "noaa"