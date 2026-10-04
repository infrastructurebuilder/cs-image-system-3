# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``sftd-token`` launch enrollment (stage 75 step 2): what a machine of
an OPA-managed group does at first boot so the OPA server agent enrolls it.

Moved here, unchanged to the byte, from the core's two launch renderers,
which now name no agent and ask ``launch_enrollment`` for the steps of the
kind the group builder issued. The cloud-init script's hash is recorded in
every machine's launch parameters, so these lines are frozen: a change here
is a change to every machine that launches afterwards, and the golden says
so.

The enrollment token arrives by reference -- the template variable
``sft_enrollment_token`` (``launch_params.ENROLLMENT_TOKEN_VARIABLE``),
supplied at apply time and never recorded.
"""

from __future__ import annotations

from typing import Any

from cs_image_system.base.launch_enrollment import register_enrollment_kind

SFTD_TOKEN = "sftd-token"


def script_lines(params: dict[str, Any]) -> list[str]:
    return [
        "# advertise the reachable private address: the auto-discovered public",
        "# IP is unroutable when the VPC has no internet gateway (found live)",
        "PRIV_IP=$(hostname -I | awk '{print $1}')",
        "mkdir -p /etc/sft",
        "grep -q '^AccessAddress:' /etc/sft/sftd.yaml 2>/dev/null"
        " || printf 'AccessAddress: %s\\n' \"$PRIV_IP\" >> /etc/sft/sftd.yaml",
        "# identity enrollment trigger (token supplied at apply time, never recorded)",
        "%{ if sft_enrollment_token != \"\" }",
        "mkdir -p /var/lib/sftd",
        "printf '%s' '${sft_enrollment_token}' > /var/lib/sftd/enrollment.token",
        "chmod 0600 /var/lib/sftd/enrollment.token",
        "systemctl restart sftd || systemctl start sftd",
        "%{ endif }",
    ]


def ansible_tasks(params: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": "sftd enrollment token (supplied at run time, never recorded)",
         "ansible.builtin.copy": {"dest": "/var/lib/sftd/enrollment.token",
                                  "content": "{{ sft_enrollment_token }}", "mode": "0600"},
         "when": "sft_enrollment_token | default('') | length > 0", "no_log": True},
        {"name": "start sftd", "ansible.builtin.service": {"name": "sftd", "state": "restarted"},
         "when": "sft_enrollment_token | default('') | length > 0"},
    ]


register_enrollment_kind(SFTD_TOKEN, script_lines=script_lines, ansible_tasks=ansible_tasks)
