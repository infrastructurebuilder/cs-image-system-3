# Backend 's3-east2' (s3) partial configuration for workspace tofu-gce
bucket = "noaa-ioos-cloud-sandbox-tfstate"
key = "statefiles/csia-image-system-test/tofu_gce.tfstate"
region = "us-east-2"
encrypt = true
use_lockfile = true
profile = "noaa"