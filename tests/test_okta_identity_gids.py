# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The engine's gid export through the Okta plugin's group builder: the
identity type ``okta`` names the plugin's registered builder, and a group
OPA holds no gid for is reported, never invented.

These two cases were in the plugin's own tests, which may not import the
engine (its surface self-check, spec 008 T009). They prove the engine's
seam through the Okta plugin, so they go with the plugin's instance suite
when it moves (spec 008, T013), and the seam itself is proven here on the
POSIX identity plugin (T035).
"""
from __future__ import annotations

import json

import pytest

from cs_image_system.okta_opa_plugin.opa_gids import OpaGidResolver


class FakeOpa:
    """Serves the OPA Attributes API: {group name: attributes payload}."""

    def __init__(self, groups):
        self.groups = groups
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url.endswith("/service_token"):
            assert method == "POST"
            payload = json.loads(body)
            assert payload == {"key_id": "k", "key_secret": "s"}
            return {"bearer_token": "tok"}
        assert method == "GET"
        assert headers["Authorization"] == "Bearer tok"
        name = url.split("/groups/")[1].split("/")[0]
        if name not in self.groups:
            import urllib.error
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        return self.groups[name]


def _live_shape(gid, group_name):
    return {"attributes": {
        "unix_gid": {"id": "x", "attribute_name": "unix_gid", "attribute_value": gid, "managed": False},
        "unix_group_name": {"id": "y", "attribute_name": "unix_group_name",
                            "attribute_value": group_name, "managed": False}}}


def _documented_shape(gid):
    return {"list": [{"id": "x", "attribute_name": "unix_gid", "attribute_value": gid, "managed": False}]}


def test_missing_gid_is_reported_not_invented():
    from cs_image_system.engine.commands import identity_gids
    fake = FakeOpa({"coops_user": _live_shape(63001, "sft_coops_user"), "tcmet_user": {"attributes": {}}})

    class Cls:
        @classmethod
        def export_gids(cls, query, groups):
            return OpaGidResolver("https://h", "t", "k", "s", transport=fake).resolve(groups)

    import cs_image_system.engine.commands.identity_gids as mod
    orig = mod.group_builder_class_for
    mod.group_builder_class_for = lambda t: Cls  # type: ignore[assignment]
    try:
        assert identity_gids.export_gids({"identity_type": "okta", "groups": "coops"}) == {"coops": "63001"}
        with pytest.raises(ValueError, match="no gid for groups \\['tcmet'\\]"):
            identity_gids.export_gids({"identity_type": "okta", "groups": "coops,tcmet"})
        assert identity_gids.export_gids({"identity_type": "okta", "groups": ""}) == {}
    finally:
        mod.group_builder_class_for = orig


def test_okta_builder_class_is_the_registered_shim():
    from cs_image_system.engine.commands.identity_gids import group_builder_class_for
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    assert group_builder_class_for("okta") is OktaTfGroupBuilder
    with pytest.raises(ValueError):
        group_builder_class_for("ldap")
