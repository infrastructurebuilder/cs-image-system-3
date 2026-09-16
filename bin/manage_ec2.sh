#!/bin/bash

# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# Initialize variables with environment variables as defaults
INSTANCE_ID="${AWS_INSTANCE_ID:-}"
PROFILE="${AWS_PROFILE:-}"
ACTION="stop" # Default action if not supplied

# Usage instruction function
usage() {
    echo "Usage: $0 [start|stop] [-i <instance-id>] [-p <aws-profile>]"
    echo "  [action] : (Optional) Action to perform: 'start' or 'stop'. Defaults to 'stop'."
    echo "  -i       : AWS EC2 Instance ID (Defaults to \$AWS_INSTANCE_ID if not supplied)"
    echo "  -p       : AWS CLI profile name (Defaults to \$AWS_PROFILE if not supplied)"
    exit 1
}

# Parse command-line arguments manually to handle flexible positioning
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo "Error: -i requires an instance ID argument."
                exit 1
            fi
            INSTANCE_ID="$2"
            shift 2
            ;;
        -p)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo "Error: -p requires a profile name argument."
                exit 1
            fi
            PROFILE="$2"
            shift 2
            ;;
        start|stop)
            ACTION="$1"
            shift
            ;;
        *)
            echo "Error: Invalid argument '$1'"
            usage
            ;;
    esac
done

# Validate that Instance ID is available (either from flag or env var)
if [ -z "$INSTANCE_ID" ]; then
    echo "Error: Instance ID is required. Provide it via -i or set the AWS_INSTANCE_ID environment variable."
    exit 1
fi

# Check if AWS CLI is installed locally
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed or not found in your PATH."
    exit 1
fi

# Build the profile argument if one was supplied or inherited via env var
PROFILE_ARG=""
if [ -n "$PROFILE" ]; then
    PROFILE_ARG="--profile $PROFILE"
fi

# Execute the requested AWS CLI command
if [ "$ACTION" == "start" ]; then
    echo "Sending start command for instance: $INSTANCE_ID..."
    aws ec2 start-instances --instance-ids "$INSTANCE_ID" $PROFILE_ARG
else
    echo "Sending stop command for instance: $INSTANCE_ID..."
    aws ec2 stop-instances --instance-ids "$INSTANCE_ID" $PROFILE_ARG
fi

# Capture the exit code of the AWS CLI command
if [ $? -eq 0 ]; then
    echo "Successfully initiated '$ACTION' for instance $INSTANCE_ID."
else
    echo "Failed to execute '$ACTION' for instance $INSTANCE_ID."
    exit 1
fi