# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 36: the frozen fixture's rosters are synthetic people.

The fixture's ``groups/`` are encrypted (stage 33) to a TEST identity that is
committed on purpose, so the encryption protects nothing and the names
themselves must be nobody's. These tests decrypt the rosters with that
identity and pin the invariants: every first and last name is drawn from the
persona lists below, every explicit address is on an example domain, every
group member or admin is a roster user, and the derived-address template
cannot produce a deliverable address. A new persona extends the lists; a real
roster cannot pass.
"""
from __future__ import annotations

import re

import pytest
import yaml

from cs_image_system.base.encryption import IDENTITY_ENV, decrypt_marker
from v2_support import FIXTURE_CONFIG

MARKER = re.compile(r"ENC\[age:[A-Za-z0-9+/=]+\]")
# phonetic-alphabet surnames, gender-neutral first names: obviously nobody
SURNAMES = {"Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliett",
            "Kilo", "Lima", "Mike", "November", "Oscar", "Papa", "Quebec", "Romeo", "Sierra"}
FIRST_NAMES = {"Avery", "Blake", "Casey", "Dakota", "Emerson", "Finley", "Greer", "Harper", "Indigo", "Jordan",
               "Kendall", "Lennox", "Morgan", "Noel", "Oakley", "Parker", "Quinn", "Riley", "Sawyer"}
EXAMPLE_DOMAINS = ("example.com", "example.net", "example.org", ".invalid", ".test")


@pytest.fixture(autouse=True)
def _fixture_identity(monkeypatch):
    monkeypatch.setenv(IDENTITY_ENV, str(FIXTURE_CONFIG / ".age-identity"))


def _plain(value: str) -> str:
    assert MARKER.fullmatch(value), f"a roster value in clear: {value!r}"
    return decrypt_marker(value)


def _users() -> list[dict]:
    return yaml.safe_load((FIXTURE_CONFIG / "groups" / "users.yaml").read_text())["users"]


def test_every_user_is_a_persona():
    for user in _users():
        assert _plain(user["first_name"]) in FIRST_NAMES, "a first name outside the persona list"
        assert _plain(user["last_name"]) in SURNAMES, "a last name outside the persona list"
        if user.get("email"):
            email = _plain(user["email"])
            assert email.endswith(EXAMPLE_DOMAINS), "an explicit address off the example domains"


def test_every_group_member_is_a_roster_user():
    names = {_plain(u["name"]) for u in _users()}
    for path in sorted((FIXTURE_CONFIG / "groups").glob("*.yaml")):
        if path.name == "users.yaml":
            continue
        for group in yaml.safe_load(path.read_text())["groups"]:
            for member in (group.get("members") or []) + (group.get("admins") or []):
                assert _plain(member) in names, f"{path.name}: {group['name']} names someone outside the roster"


def test_the_derived_address_cannot_be_delivered():
    builders = (FIXTURE_CONFIG / "cfg" / "group-builders.yml").read_text()
    templates = re.findall(r"^\s*default_user_email_template:\s*\"([^\"]+)\"", builders, flags=re.M)
    assert templates and all(t.endswith("@example.invalid") for t in templates)
    config = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "_config.yml").read_text())
    allow = config.get("public_safe", {}).get("allow", [])
    assert not any(a.endswith(".gov") for a in allow), "the fixture needs no allowance for a real domain"
