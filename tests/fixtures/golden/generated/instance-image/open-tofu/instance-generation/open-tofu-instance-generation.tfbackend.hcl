# Backend 's3-east2' (s3) partial configuration for workspace open-tofu
bucket = "noaa-ioos-cloud-sandbox-tfstate"
key = "statefiles/csia-image-system-test/open_tofu.tfstate"
region = "us-east-2"
encrypt = true
use_lockfile = true
profile = "noaa"