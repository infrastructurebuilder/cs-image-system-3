# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 70: the one-time initialisation, as terraform from an interview.

A configuration repository needs things made BEFORE its CI can run -- the
federation trusts, the repository's own settings, the secrets -- and
CI_SETUP.md tells a team how to make them by hand. This package turns the
guide's sections into terraform the team applies once, from answers it gives
once: ``cs-image-system bootstrap`` interviews (or takes every default with
``--quiet``), writes the answers to ``bootstrap.yaml`` at the root of the
tree beside ``cfg/``, and generates ``generated/bootstrap/`` from them. Every
run, dry or real, regenerates that directory from the answers file
deterministically -- generation only, never a plan or an apply -- so a
``--commit`` run commits it with the rest of the emission, ``config-drift``
reports a stale root, and a clone regenerates it without an interview.

Sections: the framework and the GitHub section live here; the clouds'
sections come from their plugins through the ``cs_image_system.bootstrap``
entry-point group, each owning the questions and the module for its cloud.
Iteration one (decision D1, 2026-09-28) is the framework and GitHub alone.
"""

from .answers import ANSWERS_FILE, read_answers, write_answers
from .facts import Facts, gather
from .generate import BOOTSTRAP_DIRNAME, output_dir, prune, regenerate, regenerate_in_run
from .interview import run_interview, terminal_ask
from .questions import Question, Refused, Rendered, Secret, Section
from .sections import ENTRY_POINT_GROUP, discover

__all__ = [
    "ANSWERS_FILE", "BOOTSTRAP_DIRNAME", "ENTRY_POINT_GROUP", "Facts", "Question", "Refused", "Rendered",
    "Secret", "Section", "discover", "gather", "output_dir", "prune", "read_answers", "regenerate",
    "regenerate_in_run", "run_interview", "terminal_ask", "write_answers",
]
