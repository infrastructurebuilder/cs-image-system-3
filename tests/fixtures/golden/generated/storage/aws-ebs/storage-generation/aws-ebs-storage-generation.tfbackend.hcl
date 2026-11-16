# Backend 's3-east1' (s3) partial configuration for workspace aws-ebs
bucket = "my-east1-tfstate-bucket"
key = "statefiles/csia/aws_ebs.tfstate"
region = "us-east-1"
encrypt = true
use_lockfile = true
profile = "noaa"