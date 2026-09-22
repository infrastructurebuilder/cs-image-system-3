# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A real run's generation-time `plan` of the identity roots runs in the
private mirror, not in the committed emission.

Found live 2026-09-22, the first real identity run after stage 51: the
Okta user lookups search by a derived address whose domain is ciphertext
in `generated/` (`first.last@ENC[age:...]`), so a plan there fails with
"no users found" for every derived user. The deferred runner already
materialises and initialises inside `_private/` before planning; the
generation-time plan now does the same. A dry run still plans nothing at
generation time and materialises nothing.
"""
from __future__ import annotations

from pathlib import Path

from tests.v2_support import V2Run


def _plans(journal: list[str]) -> list[str]:
    """The generation-time plans: a bare `plan` (the deferred one carries -out=tfplan)."""
    return [line for line in journal if line.endswith(" plan")]


def _credentials_present(monkeypatch) -> None:
    from cs_image_system.okta_opa_plugin import okta_opa_tf_group_ro_builder as rb
    from cs_image_system.okta_opa_plugin import okta_opa_tf_user_builder as ub
    monkeypatch.setattr(ub, "okta_credentials_present", lambda env=None: True)
    monkeypatch.setattr(rb, "okta_credentials_present", lambda env=None: True)


def test_a_real_run_plans_the_identity_roots_in_the_mirror_after_an_init_there(tmp_path: Path, monkeypatch):
    _credentials_present(monkeypatch)
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        run.run(["identity"], apply=False)
        journal = run.journal
        plans = _plans(journal)
        assert plans, "a real run with credentials plans the identity roots at generation time"
        private = run.config_root.resolve() / "_private"
        for line in plans:
            wd = line.split(": ", 1)[0]
            assert Path(wd).resolve().is_relative_to(private), f"planned in the emission, not the mirror: {line}"
            assert "/generated/" not in wd
            # the root was materialised from its emitted directory, then
            # initialised in the mirror (providers are not mirrored), just before
            i = journal.index(line)
            preceding = journal[:i]
            root_name = wd.rsplit("/", 1)[-1]
            materialized = [p for p in preceding if " materialize ." in p
                            and p.split(": ", 1)[0].rstrip("/").endswith(root_name)
                            and "_private" not in p.split(": ", 1)[0]]
            assert materialized, f"no materialize of the emitted root before {line}"
            init = next(p for p in reversed(preceding) if p.startswith(wd + ": ") and " init " in p)
            assert "-reconfigure" in init, "the real-run form of init, as the deferred runner's"
        roots = {line.split(": ", 1)[0].rsplit("/", 1)[-1] for line in plans}
        assert "user-generation" in roots and "group-generation" in roots
    finally:
        run.restore_cwd()


def test_a_dry_run_neither_plans_nor_materialises_at_generation(tmp_path: Path, monkeypatch):
    _credentials_present(monkeypatch)
    run = V2Run(tmp_path, monkeypatch)
    try:
        run.run(["identity"], apply=False)
        assert _plans(run.journal) == []
        assert not any(" materialize " in line for line in run.journal)
        assert not (run.config_root / "_private").exists()
    finally:
        run.restore_cwd()
