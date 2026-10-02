# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 70 step 6: the Okta and OPA section of the bootstrap -- a section
that creates nothing (decisions D4, D5, D9, D10). It reads the OPA workload
connection and role and tries the Okta API services app, and every check that
fails becomes the matching step of CI_SETUP.md 3.5. Checks are OBSERVED
questions: asked of the world on every interview, the earlier answer only a
fallback, refused by name under --quiet when neither is there.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.test_v2_bootstrap import _starter_copy

from cs_image_system.base import bootstrap as bs
from cs_image_system.base.bootstrap.questions import Refused
from cs_image_system.okta_opa_plugin import bootstrap as okta
from cs_image_system.okta_opa_plugin import okta_app_check as oac

REPO = "acme/widgets"


def _tree(tmp_path: Path, names: bool = False) -> Path:
    root = _starter_copy(tmp_path)
    gb = root / "cfg" / "group-builders.yml"
    text = gb.read_text().replace("REPLACE-ME-org", "acme").replace("REPLACE-ME-team", "acme-team")
    if names:
        text = text.replace("    org: acme", '    org: acme\n    workload_connection: "gh-widgets"\n    workload_role: "widgets-ci"', 1)
    gb.write_text(text)
    return root


def _conn(name="gh-widgets", status="ACTIVE", repository=REPO, owner="acme"):
    return {"name": name, "status": status, "conditions": [
        {"name": "repository_owner", "matcher": "EQUALS", "value": owner},
        {"name": "repository", "matcher": "EQUALS", "value": repository}]}


def _role(name="widgets-ci", connection="gh-widgets", ref: str | None = "refs/heads/main"):
    conds = [{"name": "ref", "matcher": "EQUALS", "value": ref}] if ref else []
    return {"name": name, "requirements": [{"workload_connection": {"name": connection}, "conditions": conds}]}


def _app(authenticates=True, granted=("okta.users.read", "okta.groups.read"), readable=False):
    return oac.AppCheck(client_id="0oa-test", authenticates=authenticates, granted=list(granted),
                        requested=list(granted), readable=readable)


@pytest.fixture
def world(monkeypatch):
    """The OPA listings and the Okta app the section sees; set them per test."""
    state: dict = {"listings": ([_conn()], [_role()]), "app": _app(), "asked": []}

    def listings(api_host, team):
        state["asked"].append((api_host, team))
        return state["listings"]
    monkeypatch.setattr(okta, "LISTINGS", listings)
    monkeypatch.setattr(okta, "CHECK_APP", lambda org, base="okta.com": state["app"])
    return state


def _facts(root: Path):
    return bs.gather(root, gh=False)


def _section():
    return next(s for s in bs.discover() if s.name == "okta")


def _ask(root: Path, **kw):
    return bs.run_interview([_section()], _facts(root), quiet=True, **kw)["okta"]


# ------------------------------------------------------------- the section itself

def test_the_section_is_the_okta_plugins_and_wanted_where_opa_groups_are_managed(tmp_path: Path, world):
    assert [s.name for s in bs.discover()] == ["github", "aws", "gcp", "okta"]
    assert _section().wanted_default(_facts(_tree(tmp_path))) is True
    bare = tmp_path / "bare"
    (bare / "cfg").mkdir(parents=True)
    (bare / "cfg" / "group-builders.yml").write_text("group_builders:\n  - name: ro\n    type: okta-tf-ro\n")
    assert _section().wanted_default(bs.gather(bare, git=False, gh=False)) is False


def test_a_starters_placeholders_are_refused_by_name(tmp_path: Path, world):
    with pytest.raises(Refused, match=r"okta\.org: The Okta org name -- no default can be derived"):
        _ask(_starter_copy(tmp_path))


def test_the_reference_shape_reads_clean_and_leaves_only_what_cannot_be_seen(tmp_path: Path, world):
    """An active connection naming this repository, the role bound to it and
    pinned to main, both named on the group builder, an app that authenticates
    read-only: the only steps left are the Okta admins' confirmation and the
    service user, which is by hand by decision."""
    a = _ask(_tree(tmp_path, names=True))
    assert (a["org"], a["team"], a["api_host"]) == ("acme", "acme-team", "https://acme.pam.okta.com")   # the template rendered
    assert (a["workload_connection"], a["workload_role"]) == ("gh-widgets", "widgets-ci")
    for key in ("builder_names_them", "connection_exists", "connection_requires_repository", "connection_active",
                "role_exists", "role_bound", "role_pinned", "okta_app_authenticates", "okta_app_read_only"):
        assert a[key] is True, key
    assert a["okta_app_readable"] is False
    by_hand = _section().render(a).by_hand
    assert len(by_hand) == 2, by_hand
    assert "confirm the API services app grants no `*.manage` scope" in by_hand[0]
    assert "OPA service user" in by_hand[1]
    assert world["asked"] == [("https://acme.pam.okta.com", "acme-team")]          # one listing, cached


def test_names_are_found_by_what_they_require_when_the_builder_names_none(tmp_path: Path, world):
    world["listings"] = ([_conn("other", repository="acme/other"), _conn("found-conn")], [_role("found-role", "found-conn")])
    a = _ask(_tree(tmp_path))
    assert (a["workload_connection"], a["workload_role"]) == ("found-conn", "found-role")
    assert a["builder_names_them"] is False
    lines = _section().render(a).by_hand
    assert any('`workload_connection: "found-conn"` and `workload_role: "found-role"`' in ln for ln in lines)


def test_each_failed_check_becomes_its_guide_step(tmp_path: Path, world):
    world["listings"] = ([_conn(status="DRAFT", repository="acme/other")], [_role(ref=None)])
    world["app"] = _app(granted=("okta.users.read", "okta.users.manage"))
    lines = " | ".join(_section().render(_ask(_tree(tmp_path, names=True))).by_hand)
    assert "does not require `repository` and `repository_owner`" in lines and "step 1" in lines
    assert "Activate the workload connection `gh-widgets`" in lines and "step 5" in lines
    assert "add the condition `ref` Equals `refs/heads/main` to the workload role `widgets-ci`" in lines
    assert "was granted a `*.manage` scope" in lines


def test_nothing_standing_suggests_names_and_prints_every_step(tmp_path: Path, world):
    world["listings"] = ([], [])
    world["app"] = _app(authenticates=False)
    a = _ask(_tree(tmp_path))
    assert (a["workload_connection"], a["workload_role"]) == ("github-widgets", "widgets-ci")   # suggested from the repository
    assert a["connection_exists"] is False and "connection_active" not in a                    # a check that cannot apply is not asked
    lines = " | ".join(_section().render(a).by_hand)
    for needle in ("Create the workload connection `github-widgets` as a DRAFT", "Create the workload role `widgets-ci`",
                   "Name them on", "did not authenticate with its key and scopes"):
        assert needle in lines, needle


def test_checks_are_observed_again_and_refused_when_the_world_cannot_be_asked(tmp_path: Path, world):
    root = _tree(tmp_path, names=True)
    prior = {"okta": {**_ask(root), "connection_active": False, "role_pinned": False}}    # recorded when they were not
    again = bs.run_interview([_section()], _facts(root), quiet=True, prior=prior)["okta"]
    assert again["connection_active"] is True and again["role_pinned"] is True             # the world, not the record
    world["listings"] = None                                                               # OPA cannot be asked now
    fallback = bs.run_interview([_section()], _facts(root), quiet=True, prior=prior)["okta"]
    assert fallback["connection_active"] is False                                          # the record is the fallback
    with pytest.raises(Refused, match=r"okta\.connection_exists: .* \(OPA could not be asked"):
        _ask(_tree(tmp_path / "fresh", names=True))                                         # and with no record: refused


def test_the_root_gains_no_terraform_only_the_findings(tmp_path: Path, world):
    root = _tree(tmp_path, names=True)
    gh = bs.run_interview(bs.discover(), _facts(root), quiet=True, only=["github", "okta"])
    bs.write_answers(root / bs.ANSWERS_FILE, gh)
    bs.regenerate(root)
    out = bs.output_dir(root)
    assert "okta" not in (out / "main.tf").read_text() and "oktapam" not in (out / "providers.tf").read_text()
    readme = (out / "README.md").read_text()
    assert "- **okta**" in readme and "the workload connection `gh-widgets` exists (active: yes" in readme
    assert "OPA service user" in readme and "workload connection and role (CI_SETUP.md 3.5 steps 1-2" not in readme


# --------------------------------------------------------------- the app check

def _key(tmp_path: Path) -> "tuple[bytes, rsa.RSAPublicKey]":
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return pem, key.public_key()


def test_the_client_assertion_is_an_rs256_jwt_the_public_key_verifies(tmp_path: Path):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    pem, public = _key(tmp_path)
    jwt = oac.client_assertion("0oa-id", pem, "kid-1", "https://acme.okta.com/oauth2/v1/token")
    head, body, sig = jwt.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)                                                # noqa: E731
    header = json.loads(base64.urlsafe_b64decode(pad(head)))
    claims = json.loads(base64.urlsafe_b64decode(pad(body)))
    assert header == {"alg": "RS256", "typ": "JWT", "kid": "kid-1"}
    assert claims["iss"] == claims["sub"] == "0oa-id" and claims["aud"].endswith("/oauth2/v1/token")
    assert claims["exp"] - claims["iat"] == 300
    public.verify(base64.urlsafe_b64decode(pad(sig)), f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())


def test_the_app_check_reads_the_token_and_reports_what_it_cannot_see(tmp_path: Path):
    pem, _ = _key(tmp_path)
    key_file = tmp_path / "key.pem"
    key_file.write_bytes(pem)
    env = {"OKTA_API_CLIENT_ID": "0oa-id", "OKTA_API_PRIVATE_KEY": str(key_file),     # a path works as well as the PEM
           "OKTA_API_PRIVATE_KEY_ID": "kid-1", "OKTA_API_SCOPES": "okta.users.read,okta.groups.read"}
    calls: list[tuple[str, str]] = []

    def http(method, url, headers, body):
        calls.append((method, url))
        if url.endswith("/oauth2/v1/token"):
            form = body.decode()
            assert "grant_type=client_credentials" in form and "client_assertion=" in form
            assert "scope=okta.users.read+okta.groups.read" in form
            return 200, {"access_token": "t", "scope": "okta.users.read okta.groups.read"}
        return 403, {"errorCode": "E0000006"}
    r = oac.check_app("acme", "okta.com", env, http)
    assert r.authenticates and r.read_only and r.readable is False
    assert calls == [("POST", "https://acme.okta.com/oauth2/v1/token"), ("GET", "https://acme.okta.com/api/v1/apps/0oa-id")]
    refused = oac.check_app("acme", "okta.com", env, lambda m, u, h, b: (401, {"error": "invalid_client"}))
    assert refused.authenticates is False and "401: invalid_client" in refused.error
    nothing = oac.check_app("acme", "okta.com", {}, http)
    assert nothing.authenticates is None and "no credentials to try" in nothing.error
