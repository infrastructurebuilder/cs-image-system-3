# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The GCP session as the preflight reads it: the runtime's answer to the
contract's ``session_status`` hook. Application Default Credentials are a
file (``GOOGLE_APPLICATION_CREDENTIALS``, else gcloud's default path); an
impersonated or authorized-user ADC refreshes itself, so only its
presence is reported, never a value and never an expiry. Nothing is asked
of the cloud."""
from __future__ import annotations

import json
import os
from pathlib import Path

from cs_image_system.contract.session import SessionStatus

#: the environment names this runtime's tools read credentials from
CREDENTIAL_ENVIRONMENT_PREFIXES: tuple[str, ...] = ("GOOGLE_", "CLOUDSDK_")
#: the command that makes (or renews) the operator's ADC
ADC_LOGIN = "gcloud auth application-default login"


def adc_path() -> Path:
    return Path(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                or Path.home() / ".config" / "gcloud" / "application_default_credentials.json")


def session_status() -> SessionStatus:
    """Whether Application Default Credentials exist, and of which kind."""
    path = adc_path()
    if not path.exists():
        return SessionStatus("ADC", None, f"no Application Default Credentials found ({ADC_LOGIN})", present=False,
                             renew=ADC_LOGIN)
    try:
        kind = str(json.loads(path.read_text()).get("type") or "unknown")
    except (ValueError, OSError):
        kind = "unreadable"
    return SessionStatus(f"ADC {kind}", None, "refreshes itself (no fixed expiry readable)", renews=True, renew=ADC_LOGIN)
