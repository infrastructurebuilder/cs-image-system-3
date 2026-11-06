# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 121 item 2: the core names no runtime. The preflight prints what a
runtime class answers the contract's ``session_status`` hook with, the
credential prefixes are the union of what the runtimes declare, and the
load-failure classifier asks every registered builder class -- so a runtime
class registered in a throwaway registry, with no plugin behind it, gets a
session line and a one-line load failure without the core knowing its name.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from v2_support import reset_singletons

PROVIDER_WORDS = re.compile(r"(?i)\baws\b|ami-|boto|\bsso\b|amazon-ebs|\bgcloud\b|\bgce\b|\bdocker\b")


class StubError(RuntimeError):
    """The stub's own failure, which only the stub recognises."""


def _stub_classes():
    from cs_image_system.base.commands import preflight
    from cs_image_system.contract.session import LoadFailureReport, SessionStatus
    expiry = preflight.soon(12)                 # ONE instant: two entries on one ticket are one session

    class StubModel:
        pass

    class StubRuntime:
        @classmethod
        def csis_name(cls) -> str:
            return "stub"

        @classmethod
        def session_status(cls, settings, executables):
            return SessionStatus(f"ticket {settings['ticket']}", expiry, "read from the stub's own cache",
                                 renew="stub login")

        @classmethod
        def credential_environment_prefixes(cls):
            return ("STUB_",)

        @classmethod
        def classify_failure(cls, exc):
            if isinstance(exc, StubError):
                return LoadFailureReport("environment", [f"the configuration cannot load: {exc}", "(stub login)"], code=2)
            return None

    return StubModel, StubRuntime


def test_preflight_prints_the_session_a_stub_runtime_class_answers(tmp_path):
    from cs_image_system.base import registry
    from cs_image_system.base.commands import load_failures, preflight
    from cs_image_system.contract.constants import VCT
    StubModel, StubRuntime = _stub_classes()
    reset_singletons()
    reg = cast(Any, registry.current_registry())                    # a throwaway registration: no plugin behind it
    reg.models[registry.RegistrationKey(VCT.RUNTIME_BUILDER, "test", "stub")] = StubRuntime
    reg.builders[StubModel] = StubRuntime
    try:
        root = tmp_path / "tree"
        (root / "cfg").mkdir(parents=True)
        (root / "cfg" / "runtime-builders.yml").write_text(
            "runtime_builders:\n"
            "  - name: one\n    type: stub\n    ticket: t1\n"
            "  - name: two\n    type: stub\n    ticket: t1\n"
            "  - name: odd\n    type: nobody-answers-to-this\n")
        lines, blocking, expired = preflight.raw_session_lines(root)
        assert len(lines) == 1, lines                                       # one line per SOURCE; the unknown type is skipped
        assert lines[0].startswith("session: one, two (stub, ticket t1): expires in 12 min -- SHORTER than the expected run (30 min) at ")
        assert blocking == lines and not expired
        infos = preflight.raw_session_infos(root)
        assert infos[0].renew == "stub login" and infos[0].judged and infos[0].provider == "stub"
        # the credential prefixes are the core's own plus every runtime's
        assert "STUB_" in preflight.credential_environment_prefixes()
        assert preflight.empty_environment_credentials({"STUB_TOKEN": "", "TF_VAR_X": "", "HOME": "", "STUB_OK": "1"}) == \
            ["STUB_TOKEN", "TF_VAR_X"]
        # the load-failure classifier asks the stub, down the cause chain
        wrapped = RuntimeError("loading")
        wrapped.__cause__ = StubError("the stub's ticket lapsed")
        failure = load_failures.classify_load_failure(wrapped)
        assert failure is not None and failure.kind == "environment" and failure.code == 2
        assert failure.lines == ["the configuration cannot load: the stub's ticket lapsed", "(stub login)"]
        assert load_failures.classify_load_failure(RuntimeError("nobody's")) is None
    finally:
        reset_singletons()


def test_the_core_preflight_and_classifier_name_no_provider():
    from cs_image_system.base.commands import load_failures, preflight
    for module in (preflight, load_failures):
        text = Path(str(module.__file__)).read_text()
        hits = [ln for ln in text.splitlines() if PROVIDER_WORDS.search(ln)]
        assert not hits, f"{module.__name__} names a provider: {hits}"
