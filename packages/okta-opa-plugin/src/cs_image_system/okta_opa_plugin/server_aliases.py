# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The alias block of ``sftd.yaml`` (this plugin's since the core
stopped naming the agent).

OPA ranks a record's Cloud Instance ID and Hostname above its ``AltNames``,
and the launch script overwrites the provider's own hostname with the
declared name before ``sftd`` enrolls, so the names a machine should also
answer to -- the bare declared name, the pool alias, the provider's
``ip-...`` label -- are given back afterwards as an ``AltNames`` block in
``/etc/sft/sftd.yaml``. The core decides which names, when and on which
machine (``provider_aliases``); the group builder's
``alias_registration_script`` renders the script below, which is the only
place the file and the agent are named.
"""

from __future__ import annotations

from cs_image_system.contract.launch_vocabulary import hostname_problems
from cs_image_system.contract.group import ALIASES_CHANGED, ALIASES_UNCHANGED

SFTD_YAML = "/etc/sft/sftd.yaml"


def alt_names_script(names: list[str]) -> str:
    """Rewrite the ``AltNames`` block of sftd.yaml -- kept LAST in the file,
    so it can be replaced from its heading to the end -- and restart sftd
    only when the block actually changed. Idempotent: the same names twice
    print the contract's ``ALIASES_UNCHANGED`` and touch nothing. Every
    name was validated as a hostname label (letters, digits, hyphens), so
    nothing is quoted.

    The bake truncates this file (``Labels:``) and the launch appends
    ``AccessAddress`` only when absent; this joins the second pattern and
    never truncates."""
    for n in names:
        if hostname_problems(n):
            raise ValueError(f"refusing to write {n!r} as an alias: not a hostname label")
    if names:
        want = "AltNames:\\n" + "".join(f"  - {n}\\n" for n in names)
        want_line = f"want=\"$(printf '{want}')\""
    else:
        want_line = 'want=""'
    return "\n".join([
        "set -eu",
        f"f={SFTD_YAML}",
        "sudo mkdir -p /etc/sft && sudo touch \"$f\"",
        want_line,
        "cur=\"$(sudo sed -n '/^AltNames:/,$p' \"$f\")\"",
        f"if [ \"$cur\" = \"${{want%$'\\n'}}\" ]; then echo {ALIASES_UNCHANGED}; exit 0; fi",
        "sudo sed -i '/^AltNames:/,$d' \"$f\"",
        "[ -n \"$want\" ] && printf '%s' \"$want\" | sudo tee -a \"$f\" >/dev/null",
        "sudo systemctl restart sftd",
        f"echo {ALIASES_CHANGED}",
    ])
