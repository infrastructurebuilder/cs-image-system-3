# Backend 's3-east1' (s3) partial configuration for workspace aws-efs
bucket = "my-east1-tfstate-bucket"
key = "statefiles/csia/aws_efs.tfstate"
region = "us-east-1"
encrypt = true
use_lockfile = true
profile = "noaa"