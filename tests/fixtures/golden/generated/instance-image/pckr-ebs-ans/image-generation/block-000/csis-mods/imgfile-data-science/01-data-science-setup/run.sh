#!/bin/sh
set -eu
cd "$(dirname "$0")"
command -v ansible-playbook >/dev/null 2>&1 || { echo 'ansible-playbook not present on this image; cannot re-run' >&2; exit 3; }
ansible-playbook -i localhost, -c local 'setup_data_science.yml'
