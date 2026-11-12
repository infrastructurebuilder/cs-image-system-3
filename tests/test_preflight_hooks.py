# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The core names no runtime. The preflight prints what a
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

PROVIDER_WORDS = re.compile(r"(?i)\baws\b|ami-|boto|\bsso\b|amazon-ebs|\bgcloud\b|\bgce\b|\bdocker\b")


class StubError(RuntimeError):
    """The stub's own failure, which only the stub recognises."""


def _stub_classes():
    from cs_image_system.base.commands import preflight
    from cs_image_system.contract.session import LoadFailureReport, SessionStatus
    expiry = preflight.soon(12)                 # ONE instant: two entries on one ticket are one session

    class StubModel:
        type: str = "stub"
        ticket: str = ""

    class StubRuntime:
        model: Any = None

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
    reg = cast(Any, registry.Registry())                            # a registry of the test's own: no plugin behind the stub
    reg.models[registry.RegistrationKey(VCT.RUNTIME_BUILDER, "test", "stub")] = StubRuntime
    reg.builders[StubModel] = StubRuntime
    # the sessions are read over the LOADED configuration (nothing
    # reads the raw tree before a load): a context whose runtime
    # builders are two stub instances on one ticket, each over its model
    from types import SimpleNamespace

    def entry(ticket: str):
        model = StubModel()
        model.type = "stub"
        model.ticket = ticket
        builder = StubRuntime()
        builder.model = model
        return builder
    ctx = SimpleNamespace(runtime_builders={"one": entry("t1"), "two": entry("t1")}, state_backends={},
                          executables={}, config={}, reg=reg)
    lines, blocking = preflight.session_lines(ctx)
    assert len(lines) == 1, lines                                       # one line per SOURCE
    assert lines[0].startswith("session: one, two") and "12 min" in lines[0] and "SHORTER" in lines[0]
    assert blocking == lines
    _, absent, expired, _, unjudged = preflight.session_readiness(ctx)
    assert not absent and not expired and not unjudged
    infos = preflight.session_infos(ctx)
    assert infos[0].renew == "stub login" and infos[0].judged and infos[0].provider == "stub"
    # the credential prefixes are the core's own plus every runtime's registered in the run's registry
    assert "STUB_" in preflight.credential_environment_prefixes(reg)
    assert preflight.empty_environment_credentials(reg, {"STUB_TOKEN": "", "TF_VAR_X": "", "HOME": "", "STUB_OK": "1"}) == \
        ["STUB_TOKEN", "TF_VAR_X"]
    # the load-failure classifier asks the stub, down the cause chain
    wrapped = RuntimeError("loading")
    wrapped.__cause__ = StubError("the stub's ticket lapsed")
    failure = load_failures.classify_load_failure(wrapped, reg)
    assert failure is not None and failure.kind == "environment" and failure.code == 2
    assert len(failure.lines) == 2 and "cannot load" in failure.lines[0] and "lapsed" in failure.lines[0]
    assert failure.lines[1] == "(stub login)"
    assert load_failures.classify_load_failure(RuntimeError("nobody's"), reg) is None


def test_the_core_preflight_and_classifier_name_no_provider():
    from cs_image_system.base.commands import load_failures, preflight
    for module in (preflight, load_failures):
        text = Path(str(module.__file__)).read_text()
        hits = [ln for ln in text.splitlines() if PROVIDER_WORDS.search(ln)]
        assert not hits, f"{module.__name__} names a provider: {hits}"
