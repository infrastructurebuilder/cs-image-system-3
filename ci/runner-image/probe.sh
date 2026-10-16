#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0
# The runner image's probe (stage 92): every tool a configuration's CI calls
# answers --version from the path cfg/executables.yml pins (or from PATH where
# the starters pin no path), and the version is the one /etc/csis-ci/tools.txt
# lists. Run at build time, by the build-and-probe leg of full-test, and by
# anyone who doubts an image: `docker run --rm <image> csis-ci-probe`.
set -euo pipefail
want() { awk -v k="$1" '$1 == k {print $2}' /etc/csis-ci/tools.txt; }
check() {   # check <tool> <path> <version command> <expected substring>
  local tool=$1 path=$2 cmd=$3 expect=$4 out
  [ -x "$path" ] || { echo "csis-ci-probe: $tool: $path is not executable" >&2; return 1; }
  out=$(eval "$cmd" 2>&1 | head -3 | tr '\n' ' ')
  case "$out" in *"$expect"*) printf 'csis-ci-probe: %-24s %s\n' "$tool" "$expect" ;;
    *) echo "csis-ci-probe: $tool: wanted $expect, got: $out" >&2; return 1 ;; esac
}
status=0
check uv      /usr/local/bin/uv      "uv --version"                   "$(want uv)" || status=1
check just    /usr/local/bin/just    "just --version"                 "$(want just)" || status=1
check tofu    /usr/local/bin/tofu    "tofu version"                   "v$(want tofu)" || status=1
check packer  /usr/local/bin/packer  "packer version"                 "v$(want packer)" || status=1
check aws     /usr/local/bin/aws     "aws --version"                  "aws-cli/$(want aws-cli)" || status=1
check session-manager-plugin /usr/local/bin/session-manager-plugin "session-manager-plugin --version" "$(want session-manager-plugin)" || status=1
check gcloud  /usr/local/bin/gcloud  "gcloud --version"               "Google Cloud SDK $(want gcloud)" || status=1
check sft     /usr/bin/sft           "sft --version"                  "$(want sft)" || status=1
check docker  /usr/local/bin/docker  "docker --version"               "$(want docker-cli)" || status=1
check ansible-playbook /usr/local/bin/ansible-playbook "ansible-playbook --version" "core $(want ansible-core)" || status=1
check yq      /usr/local/bin/yq      "yq --version"                   "v$(want yq)" || status=1
check age     /usr/local/bin/age     "age --version"                  "v$(want age)" || status=1
check bash    /usr/local/bin/bash    "bash --version"                 "version 5." || status=1
check jq      /usr/local/bin/jq      "jq --version"                   "jq-$(want jq)" || status=1
check git     /usr/bin/git           "git --version"                  "git version 2." || status=1
check python  /usr/local/bin/uv      "uv python find $(want python)"  "/opt/uv/python" || status=1
check node    /usr/bin/node          "node --version"                 "v$(want node)." || status=1
exit $status
