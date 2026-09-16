# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Suite-wide isolation.

The preflight (stage 12.3) reads the operator's credential caches
(`~/.aws/sso/cache`, the gcloud ADC file). A test must never read the
developer's real caches -- an expired real session would fail the headless
CLI tests on one machine and pass on another -- so every test sees an
empty AWS dir and no ADC unless it fakes its own (a test's monkeypatch
wins over this fixture).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_credential_caches(tmp_path_factory, monkeypatch):
    d = tmp_path_factory.mktemp("aws-empty")
    (d / "config").write_text("")
    monkeypatch.setenv("CSIS_AWS_DIR", str(d))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(d / "no-adc.json"))
    yield
