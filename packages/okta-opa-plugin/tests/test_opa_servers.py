# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 55: the OPA server registry, read and retired through the resolver
with an injected transport -- no network.

The path is the one that answers live: servers live under the RESOURCE
GROUP (``/resource_groups/{rg}/projects/{prj}/servers``); the team-level
``/projects/...`` path answers 401. And ``None`` from the listing means the
service could not be asked, which is never the same as an empty registry.
"""
from __future__ import annotations

import urllib.error
from email.message import Message

import pytest

from cs_image_system.okta_opa_plugin.opa_gids import OpaGidResolver

TEAM = "/v1/teams/t"
PREFIX = f"{TEAM}/resource_groups/rg-1/projects/prj-1"


class FakeOpa:
    def __init__(self, servers=None, *, projects_missing=False, fail_servers=False):
        self.calls: list[tuple[str, str]] = []
        self.servers = list(servers or [])
        self.projects_missing = projects_missing
        self.fail_servers = fail_servers

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        path = url.split("https://h", 1)[1]
        if path.endswith("/service_token"):
            return {"bearer_token": "tok"}
        if path == f"{TEAM}/resource_groups":
            return {"list": [{"id": "rg-1", "name": "coops_rg"}, {"id": "rg-9", "name": "other_rg"}]}
        if path == f"{TEAM}/resource_groups/rg-1/projects":
            return {"list": [] if self.projects_missing else [{"id": "prj-1", "name": "coops_rg_login"}]}
        if path == f"{PREFIX}/servers" and method == "GET":
            if self.fail_servers:
                raise urllib.error.HTTPError(url, 503, "unavailable", Message(), None)
            return {"list": self.servers}
        if path.startswith(f"{PREFIX}/servers/") and method == "DELETE":
            sid = path.rsplit("/", 1)[1]
            if not any(s["id"] == sid for s in self.servers):
                raise urllib.error.HTTPError(url, 404, "not found", Message(), None)
            self.servers = [s for s in self.servers if s["id"] != sid]
            return {}   # 204: empty body
        raise AssertionError(f"unexpected {method} {path}")


def _r(fake) -> OpaGidResolver:
    return OpaGidResolver("https://h", "t", "k", "s", transport=fake)


LIVE = [{"id": "10ff7662", "hostname": "coops-model", "access_address": "10.26.34.156"},
        {"id": "772d4058", "hostname": "coops-model", "access_address": "10.26.35.236"},
        {"id": "aaaa0000", "hostname": "other-box", "access_address": "10.26.35.1"}]


def test_servers_are_read_under_the_resource_group_path():
    fake = FakeOpa(LIVE)
    got = _r(fake).registered_servers("coops")
    assert got is not None
    assert [(s["hostname"], s["address"], s["id"]) for s in got] == [
        ("coops-model", "10.26.34.156", "10ff7662"),
        ("coops-model", "10.26.35.236", "772d4058"),
        ("other-box", "10.26.35.1", "aaaa0000")]
    assert ("GET", f"https://h{PREFIX}/servers") in fake.calls
    assert not any("/v1/teams/t/projects/" in u for _, u in fake.calls)   # the 401 path, never


def test_an_unaskable_registry_is_none_not_empty():
    """Stage 57's rule, here: silence is not a free name."""
    assert _r(FakeOpa(fail_servers=True)).registered_servers("coops") is None
    assert _r(FakeOpa(projects_missing=True)).registered_servers("coops") is None
    assert _r(FakeOpa([])).registered_servers("coops") == []


def test_retire_deletes_one_registration_and_a_404_counts_as_gone():
    fake = FakeOpa(LIVE)
    r = _r(fake)
    assert r.retire_server("coops", "772d4058") is True
    assert ("DELETE", f"https://h{PREFIX}/servers/772d4058") in fake.calls
    assert [s["id"] for s in fake.servers] == ["10ff7662", "aaaa0000"]
    assert r.retire_server("coops", "772d4058") is True     # already gone


def test_retire_raises_when_the_project_cannot_be_found():
    with pytest.raises(ValueError, match="not found; cannot retire"):
        _r(FakeOpa(projects_missing=True)).retire_server("coops", "x")


def test_retire_does_not_swallow_a_real_failure():
    class Broken(FakeOpa):
        def __call__(self, method, url, headers, body):
            if method == "DELETE":
                raise urllib.error.HTTPError(url, 500, "boom", Message(), None)
            return super().__call__(method, url, headers, body)
    with pytest.raises(urllib.error.HTTPError):
        _r(Broken(LIVE)).retire_server("coops", "10ff7662")


def test_enrollment_tokens_still_walk_the_same_project():
    """The refactor moved the rg -> project walk into one place; the older
    caller must still land on the same prefix."""
    class WithTokens(FakeOpa):
        def __call__(self, method, url, headers, body):
            path = url.split("https://h", 1)[1]
            if path == f"{PREFIX}/server_enrollment_tokens":
                self.calls.append((method, url))
                return {"list": [{"description": "coops launch"}]}
            return super().__call__(method, url, headers, body)
    assert _r(WithTokens()).project_enrollment_tokens("coops") == ["coops launch"]
