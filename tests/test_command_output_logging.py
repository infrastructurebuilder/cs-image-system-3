# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the log says about a command the process ran.

The summary line reaches INFO with colour codes stripped, stderr too; a
long output is cut to its tail, with the whole at DEBUG; a verdict line the
tail would cut is shown ahead of it, by line number, and a verdict inside
the tail is shown once, with it.

history: bundle VIII item 3, XII item 8.
"""
from __future__ import annotations

import logging
import subprocess


def test_a_command_the_process_ran_has_its_output_logged(caplog):
    from cs_image_system.base.models.executable import ExecutableModel
    script = 'printf "x\\n\\033[1mPlan:\\033[0m 0 to add, 1 to change, 0 to destroy.\\n"; echo "a warning" >&2'
    e = ExecutableModel(name="sh", binary="/bin/sh", args=["-c", script])
    with caplog.at_level(logging.INFO):
        res = e.execute()
    assert res.returncode == 0
    assert "Plan: 0 to add, 1 to change, 0 to destroy." in caplog.text        # the summary line reaches INFO
    assert "\x1b[" not in caplog.text                                            # colour codes stripped
    assert "a warning" in caplog.text                                            # stderr too
    caplog.clear()
    long = ExecutableModel(name="sh", binary="/bin/sh", args=["-c", "seq 1 50"])
    with caplog.at_level(logging.INFO):
        long.execute()
    assert "last 40 of 50" in caplog.text
    assert "\n50" in caplog.text and "\n5\n" not in caplog.text.split("all at DEBUG")[1]


def test_a_verdict_line_cut_by_the_tail_is_shown_ahead_of_it(caplog):
    from cs_image_system.base.models.executable import _log_captured
    outputs = "\n".join(f"output_{i} = \"v\"" for i in range(45))
    stdout = "Apply complete! Resources: 1 added, 0 changed, 0 destroyed.\n\nOutputs:\n\n" + outputs + "\n"
    with caplog.at_level(logging.INFO):
        _log_captured(["tofu", "apply"], subprocess.CompletedProcess(["tofu", "apply"], 0, stdout, ""))
    assert "1: Apply complete!" in caplog.text, "the verdict, with its line number"
    assert caplog.text.index("Apply complete!") < caplog.text.index("last 40 of 49"), "ahead of the tail"
    caplog.clear()
    short = "Plan: 0 to add, 0 to change, 1 to destroy.\nx\n"
    with caplog.at_level(logging.INFO):
        _log_captured(["tofu", "plan"], subprocess.CompletedProcess(["tofu", "plan"], 0, short, ""))
    assert caplog.text.count("Plan: 0 to add") == 1, "a verdict inside the tail is shown once, with it"
