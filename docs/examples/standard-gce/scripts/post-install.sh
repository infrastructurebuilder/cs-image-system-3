#!/usr/bin/env bash
# docs/examples/standard-gce/scripts/post-install.sh -- a script file the
# `site-files` bash-remote modification runs after its `ensure` steps
# (copied beside the packer root; content-hashed into the image's lineage).
set -euo pipefail
echo "team-node post-install: $(cat /etc/team-node.conf)"
