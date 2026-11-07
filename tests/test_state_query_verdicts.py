# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The verdicts the state query gives, and how a provider's answer becomes one.

A group the identity provider could not be asked about is `unavailable`,
never a missing group; a 404 is still a real absence and hard drift. A
permission refusal is marked REFUSED, a role's gap, not a cloud that did
not answer. A group's OPA objects rewritten in place are `changed` (soft),
absent ones `missing` (soft), a silent OPA says nothing; the builder's real
`query_state` attaches that record from the resource-group and policy
listings. A pinned instance never launched is a note and the cloud is not
asked; an instance whose storage root has no state yet is a note.

history: bundle V item 1, XII items 9, 13 and 33, XIV item 6.
"""
from __future__ import annotations

import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from cs_image_system.base import state_query as sq
from cs_image_system.base.read_models import identity_read_model
from cs_image_system.okta_opa_plugin import okta_opa_tf_group_builder as gbmod
from cs_image_system.okta_opa_plugin.opa_gids import GID_ATTRIBUTE
from tests.harness import V2Run

# captured at import, before the harness's stub replaces it on the class
_REAL_QUERY_STATE = gbmod.OktaTfGroupBuilder.query_state


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch)
    try:
        yield r
    finally:
        r.restore_cwd()


def _group_builder(ctx) -> gbmod.OktaTfGroupBuilder:
    return next(b for b in ctx.group_builders.values() if isinstance(b, gbmod.OktaTfGroupBuilder))


def _http(code: int, reason: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://opa.invalid", code, reason, Message(), None)


# ------------------------------------------------------- unavailable, not missing

def test_a_group_the_provider_could_not_be_asked_about_is_unavailable_not_missing(run):
    ctx = run.ctx
    ctx.meta_state.write_identity_read_model(identity_read_model(ctx))
    seen = ctx.meta_state.identity_read_model()          # an absence is hard
    for rec in seen["groups"].values():                 # only for a group the provider was SEEN to carry
        rec["seen"] = True
    ctx.meta_state.write_identity_read_model(seen)
    names = sorted(ctx.meta_state.identity_read_model()["groups"])
    groups = {names[0]: {"present": False, "error": "HTTP 401 Unauthorized"},
              names[1]: {"present": False}}
    report = sq.StateReport(run=ctx.run_id)
    by_name = {d.name: d for d in sq.group_drift(ctx, groups, report)}
    assert names[0] not in by_name, "an errored record is not drift of any kind"
    assert f"groups/{names[0]}: HTTP 401 Unauthorized" in report.unavailable
    assert by_name[names[1]].drift == sq.DRIFT_MISSING and by_name[names[1]].hard, "a plain absence is still hard"
    # the query routes it the same way, and the strict query still refuses (unavailable is not `stale`)
    assert names[0] not in {d.name for d in sq.group_drift(ctx, groups)}


def test_the_builder_tells_a_404_from_a_call_that_failed(run, monkeypatch):
    gb = _group_builder(run.ctx)
    names = [g.get_name() for g in gb.get_groups_for_builder()]
    assert len(names) >= 3
    monkeypatch.setattr(gbmod, "credentials_from_env", lambda team: ("k", "s"))
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "can_manage_workload_access", lambda self: False)
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_users", lambda self, g: None)
    monkeypatch.setattr(gbmod.OpaGidResolver, "project_enrollment_tokens", lambda self, g: None)
    monkeypatch.setattr(gbmod.OpaGidResolver, "security_policies", lambda self: None)   # silent, never asked
    monkeypatch.setattr(gbmod.OpaGidResolver, "resource_groups", lambda self: None)

    def attributes(self, server_group):
        if server_group == f"{names[0]}{gbmod.USER_GROUP_SUFFIX}":
            raise _http(404, "Not Found")
        if server_group == f"{names[1]}{gbmod.USER_GROUP_SUFFIX}":
            raise _http(401, "Unauthorized")
        if server_group == f"{names[2]}{gbmod.USER_GROUP_SUFFIX}":
            raise OSError("Connection refused")
        return {GID_ATTRIBUTE: 180000, gbmod.GROUP_NAME_ATTRIBUTE: server_group}
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_attributes", attributes)
    # the harness stubs query_state on the class (every group present, gid 1); this test is about the real one
    recs = _REAL_QUERY_STATE(gb)
    assert recs[names[0]] == {"present": False}, "OPA answered: the group is not there"
    assert recs[names[1]] == {"present": False, "error": "HTTP 401 Unauthorized"}
    assert recs[names[2]]["present"] is False and "Connection refused" in recs[names[2]]["error"]
    for other in names[3:]:
        assert recs[other]["present"] is True and "error" not in recs[other]


# ------------------------------------------------------- a refusal is a role's gap

def test_a_permission_refusal_is_marked_as_such_in_the_report():
    report = sq.StateReport(run="r")
    denied = Exception("An error occurred (AccessDenied) when calling the GetBucketTagging operation: User: "
                       "arn:aws:sts::1:assumed-role/csis-github-apply/GitHubActions is not authorized to perform: "
                       "s3:GetBucketTagging on resource: \"arn:aws:s3:::b\"")

    def boom():
        raise denied
    assert sq._query(report, "storages/aws-s3", boom) is None
    assert report.unavailable == [f"storages/aws-s3: {sq.REFUSED} {denied}"]
    assert "csis-github-apply" in report.unavailable[0] and "GetBucketTagging" in report.unavailable[0]
    # a cloud that did not answer is still just that
    report = sq.StateReport(run="r")

    def timeout():
        raise Exception("Read timed out. (read timeout=60)")
    sq._query(report, "storages/pd", timeout)
    assert report.unavailable == ["storages/pd: Read timed out. (read timeout=60)"]
    assert "REFUSED" not in report.render()
    # botocore's shape: the code, not only the text
    class ClientErrorLike(Exception):
        response = {"Error": {"Code": "UnauthorizedOperation", "Message": "no"}}
    assert sq.is_refusal(ClientErrorLike("You are not allowed")) and not sq.is_refusal(ValueError("no such bucket"))


# ------------------------------------------------------- a group's module objects

def test_a_rewritten_object_is_changed_and_says_who_must_let_go():
    objects = {"resource_group": {"name": "basic_rg", "present": True,
                                  "diff": ["delegated_admins: ['admin_admin'] != ['basic_admin']"]},
               "user_policy": {"name": "basic_v1_security_policy_user", "present": True,
                               "diff": ["rules[0].name: 'allow_login_admin' != 'allow_login_basic'"]},
               "admin_policy": {"name": "basic_v1_security_policy_admin", "present": True}}
    drift = sq.module_drift("basic", objects)
    assert [d.drift for d in drift] == [sq.DRIFT_CHANGED, sq.DRIFT_CHANGED] and not any(d.hard for d in drift)
    assert "'basic_rg'" in drift[0].detail and "['admin_admin'] != ['basic_admin']" in drift[0].detail
    assert "state rm" in drift[1].detail and "allow_login_admin" in drift[1].detail


def test_an_absent_object_is_missing_but_not_hard_and_silence_is_nothing():
    drift = sq.module_drift("coops", {"admin_policy": {"name": "coops_v1_security_policy_admin", "present": False}})
    assert len(drift) == 1 and drift[0].drift == sq.DRIFT_MISSING and not drift[0].hard
    assert "apply" in drift[0].detail, "the remedy is the next identity apply"
    assert sq.module_drift("coops", None) == [] and sq.module_drift("coops", {}) == []


def _opa(monkeypatch, *, policies, rgs, detail):
    monkeypatch.setattr(gbmod, "credentials_from_env", lambda team: ("k", "s"))
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "can_manage_workload_access", lambda self: False)
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_users", lambda self, g: None)
    monkeypatch.setattr(gbmod.OpaGidResolver, "project_enrollment_tokens", lambda self, g: None)
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_attributes",
                        lambda self, g: {GID_ATTRIBUTE: 180000, gbmod.GROUP_NAME_ATTRIBUTE: g})
    monkeypatch.setattr(gbmod.OpaGidResolver, "security_policies", lambda self: policies)
    monkeypatch.setattr(gbmod.OpaGidResolver, "resource_groups", lambda self: rgs)
    monkeypatch.setattr(gbmod.OpaGidResolver, "resource_group", lambda self, rg_id: detail(rg_id))


def test_the_builder_attaches_the_module_objects_and_omits_them_when_opa_is_silent(run, monkeypatch):
    gb = _group_builder(run.ctx)
    name = gb.get_groups_for_builder()[0].get_name()
    rg = {"id": "rg-1", "name": f"{name}_rg", "description": f"Resource group for Okta group {name}",
          "delegated_resource_admin_groups": [{"id": "x", "name": "someone_else_admin"}]}
    _opa(monkeypatch, policies=[], rgs=[{"id": "rg-1", "name": f"{name}_rg"}], detail=lambda rg_id: rg)
    objects = _REAL_QUERY_STATE(gb)[name]["module_objects"]
    assert objects["resource_group"]["diff"] == [f"delegated_admins: ['someone_else_admin'] != ['{name}_admin']"]
    assert objects["user_policy"] == {"name": f"{name}_v1_security_policy_user", "present": False}
    drift = sq.module_drift(name, objects)
    assert {d.drift for d in drift} == {sq.DRIFT_CHANGED, sq.DRIFT_MISSING}
    # OPA silent on either listing, or on the group's own record: nothing is said, nothing guessed
    _opa(monkeypatch, policies=None, rgs=[], detail=lambda rg_id: rg)
    assert "module_objects" not in _REAL_QUERY_STATE(gb)[name]
    _opa(monkeypatch, policies=[], rgs=[{"id": "rg-1", "name": f"{name}_rg"}], detail=lambda rg_id: None)
    assert "module_objects" not in _REAL_QUERY_STATE(gb)[name]


# ------------------------------------------------------- the notes

def test_a_pinned_instance_never_launched_is_a_note_and_the_cloud_is_not_asked(run, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    ctx = run.ctx
    rt = sorted(n for n, b in ctx.runtime_builders.items() if isinstance(b, AwsCloudBuilder))[0]
    ctx.meta_state.add_build({"build_id": "ami-fresh", "series": "imgfile-coops-model", "runtime": rt,
                              "name": "n", "parent": "external", "input_fingerprint": "f", "run": "r",
                              "capabilities": {}, "mods": [], "chain": []})
    ctx.meta_state.bind_instance("test", "ami-fresh", "run-x")      # a bake binds the pin; nothing launched

    def asked(self, name):
        raise AssertionError(f"the cloud was asked about {name}")
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", asked)
    report = sq.query_state(ctx)
    assert not [u for u in report.unavailable if "instances/test" in u]
    note = [n for n in report.notes if "instances/test" in n]
    assert note and "launched" in note[0] and "ami-fresh" in note[0], report.notes


def test_the_state_query_notes_an_instance_whose_storage_root_has_no_state_yet(run):
    report = sq.query_state(run.ctx)
    notes = [n for n in report.notes if "no state yet" in n]
    assert notes, report.notes
    assert any("mnt_data" in n for n in notes), notes
