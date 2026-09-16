# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 35: a commit-time gate over everything staged.

Fake secrets below are built by concatenation so this module never carries
one -- the gate scans test code for the hard shapes too.
"""
from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from cs_image_system.base.meta_state import commit_meta_state
from cs_image_system.base.public_safe import (
    Finding,
    PublicSafeError,
    allow_from_config,
    assert_public_safe,
    refused_path,
    scan_bytes,
    scan_staged,
    scan_tree,
    soft_exempt,
)
from v2_support import FIXTURE_CONFIG, REPO

PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIE"
AKIA = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
JWT = "ey" + "JhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.abc"
GH = "gh" + "p_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
SLACK = "xo" + "xb-" + "1234567890-abcdefghij"
AGE_ID = "AGE-SECRET-" + "KEY-1" + "Q" * 58
TOKEN44 = "Ab1" + "Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2Yz3Ab4Cd5Ef6Gh7"      # 44 mixed base64 chars
SSH_KEY = "ssh-ed25519 " + "AAAAC3NzaC1lZDI1NTE5AAAAIGwUXZbRCTmbNmM2aYK0dQtoO4XMAVhWJqL2c1x9pTqk"
LOCK_HASH = "h1:" + "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2Yz3Ab4Cd5Ef6Gh7Ij8="
ENC = "ENC[age:" + "YWdlLWVuY3J5cHRpb24ub3JnL3YxCi0+IFgyNTUxOSBKWEJhTW90dHJNRTRrNH0h" + "]"


def rules(data: str, path: str = "generated/x.tf", allow=()) -> set[str]:
    return {f.rule for f in scan_bytes(data.encode(), path, allow)}


@pytest.mark.parametrize("text,rule", [
    (PEM, "pem-private-key"), (AKIA, "aws-access-key"), (JWT, "jwt"), (GH, "github-token"),
    (SLACK, "slack-token"), (AGE_ID, "age-identity"),
    ('{"ty' + 'pe": "service_account", "private_' + 'key": "x", "private_' + 'key_id": "' + "a" * 40 + '"}', "gcp-service-account"),
    ("export TF_" + "VAR_nos_key=abcd1234", "tfvar-assignment"),
])
def test_every_hard_shape_is_refused_anywhere_including_prose_and_test_code(text, rule):
    assert rule in rules(text)
    assert rule in rules(text, "README.md")
    assert rule in rules(text, "tests/test_x.py")


@pytest.mark.parametrize("text", [
    "AKIA is a prefix", "TF_" + "VAR_nos_key=$NOS_KEY", 'TF_' + 'VAR_x="${TOKEN}"', '"ty' + 'pe": "service_account" in prose',
    "eyJ short", "-----BEGIN PUBLIC KEY-----",
])
def test_the_hard_rules_do_not_fire_on_the_negative_shapes(text):
    assert not rules(text) & set(("pem-private-key", "aws-access-key", "jwt", "gcp-service-account", "tfvar-assignment"))


def test_addresses_and_high_entropy_strings_are_soft_findings_exempt_in_prose_and_test_code():
    assert rules("contact pat.trip@vims.edu", "groups/users.yaml") == {"email"}
    assert rules("contact pat.trip@vims.edu", "docs/NOTE.md") == set()
    assert rules("contact pat.trip@vims.edu", "tests/test_users.py") == set()
    assert rules("contact pat.trip@vims.edu", "packages/base/tests/test_users.py") == set()
    assert rules("user@example.com and root@localhost", "cfg/x.yml") == set()       # example domains are not people
    assert rules(f'key = "{TOKEN44}"') == {"high-entropy"}
    assert rules(f'key = "{TOKEN44}"', "PLAN.md") == set()
    assert soft_exempt("tests/test_v2_public_safe.py") and soft_exempt("docs/history/X.md") and not soft_exempt("cfg/_config.yml")


def test_public_structures_never_fire():
    assert rules(f"admin_public_keys: ['{SSH_KEY}']", "cfg/_config.yml") == set()
    assert rules(f'hashes = ["{LOCK_HASH}"]', "generated/x/.terraform.lock.hcl") == set()
    assert rules(f"- name: {ENC}\n  email: {ENC}", "groups/users.yaml") == set()
    assert rules("recipients: [age1" + "q" * 58 + "]", "cfg/_config.yml") == set()
    assert rules("sha256: " + "0f" * 32, "meta-state/lineage.yaml") == set()       # a digest is hex


def test_the_allow_list_is_by_decision_substrings_and_whole_paths():
    allow = ["@noaa.gov", ".iam.gserviceaccount.com", "path:.age-identity"]
    assert rules("pat.trip@noaa.gov csis-runner@p.iam.gserviceaccount.com", "generated/x.tf", allow) == set()
    assert rules("pat.trip@vims.edu", "generated/x.tf", allow) == {"email"}
    assert scan_tree(FIXTURE_CONFIG, allow, files=[".age-identity"]) == []
    assert [f.rule for f in scan_tree(FIXTURE_CONFIG, [], files=[".age-identity"])] == ["age-identity"]


def test_a_zipped_plan_is_opened_and_its_members_scanned():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tfplan", b"\x00\x01binary\x00" + JWT.encode() + b"\x00")
        zf.writestr("tfstate", b'{"email": "pat.trip@vims.edu"}')
    found = scan_bytes(buf.getvalue(), "generated/x/plan.zip")
    assert {(f.path, f.rule) for f in found} == {("generated/x/plan.zip!tfplan", "jwt"),
                                                  ("generated/x/plan.zip!tfstate", "email")}


@pytest.mark.parametrize("path,refused", [
    ("generated/identity/x/tfplan", True), ("a/b/terraform.tfstate", True), ("a/terraform.tfstate.backup", True),
    ("a/prod.tfvars", True), ("a/prod.tfvars.json", True), (".envrc", True), ("cfg/.private_key.pem", True),
    ("cfg/.private_key.json", True), ("cfg/.public_key.json", True),
    ("generated/x/x.tf", False), ("meta-state/identity.yaml", False), ("a/.terraform.lock.hcl", False),
    ("a/x.tfbackend.hcl", False), ("tests/fixtures/config/.age-recipient", False),
])
def test_the_refused_paths(path, refused):
    assert refused_path(path) is refused


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "cfg"
    (repo / "meta-state").mkdir(parents=True)
    (repo / "generated" / "identity" / "ws").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.org"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    return repo


def test_a_tree_scan_sees_tracked_and_untracked_but_not_ignored_files(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".gitignore").write_text("ignored/\n")
    (repo / "ignored").mkdir()
    (repo / "ignored" / "x.tf").write_text(PEM)
    (repo / "generated" / "identity" / "ws" / "main.tf").write_text('a = "pat.trip@vims.edu"\n')
    (repo / "meta-state" / "identity.yaml").write_text("groups: {}\n")
    subprocess.run(["git", "-C", str(repo), "add", "meta-state"], check=True)
    found = scan_tree(repo)
    assert [(f.path, f.rule) for f in found] == [("generated/identity/ws/main.tf", "email")]
    assert scan_tree(repo, ["@vims.edu"]) == []


def test_the_index_is_scanned_as_it_would_be_committed(tmp_path):
    repo = _repo(tmp_path)
    f = repo / "generated" / "identity" / "ws" / "main.tf"
    f.write_text('a = "fine"\n')
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    f.write_text(PEM)                                             # the working tree is not what is staged
    assert scan_staged(repo) == []
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert [x.rule for x in scan_staged(repo)] == ["pem-private-key"]
    (repo / "generated" / "identity" / "ws" / "tfplan").write_bytes(b"PK\x03\x04junk")
    subprocess.run(["git", "-C", str(repo), "add", "-f", "generated/identity/ws/tfplan"], check=True)
    assert {x.rule for x in scan_staged(repo)} == {"pem-private-key", "refused-path"}


def test_a_run_commit_refuses_and_leaves_the_index_untouched(tmp_path, caplog):
    repo = _repo(tmp_path)
    (repo / "meta-state" / "identity.yaml").write_text("groups: {}\n")
    (repo / "generated" / "identity" / "ws" / "main.tf").write_text(f'key = "{PEM}"\n')
    with pytest.raises(PublicSafeError) as e:
        commit_meta_state(repo, repo / "generated", "run1", ["identity"], dry_run=True)
    assert "generated/identity/ws/main.tf: pem-private-key" in str(e.value)
    staged = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--name-only"],
                            check=True, capture_output=True, text=True).stdout.split()
    assert staged == []                                                          # nothing staged
    assert subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"],
                          capture_output=True).returncode != 0                     # nothing committed
    # the allow list of the configuration root is honoured
    (repo / "cfg").mkdir()
    (repo / "cfg" / "_config.yml").write_text("public_safe:\n  allow:\n    - '@vims.edu'\n")
    (repo / "generated" / "identity" / "ws" / "main.tf").write_text('a = "pat.trip@vims.edu"\n')
    assert commit_meta_state(repo, repo / "generated", "run2", ["identity"], dry_run=True)


def test_the_meta_state_backstop_is_the_same_scanner():
    assert_public_safe({"fine": ["a", {"b": "c"}]})
    with pytest.raises(PublicSafeError, match="pem-private-key"):
        assert_public_safe({"key": PEM}, where="meta-state/pins.yaml")
    with pytest.raises(PublicSafeError, match="aws-access-key"):
        assert_public_safe([AKIA], where="state report")
    assert_public_safe({"email": "pat.trip@vims.edu"})                # soft shapes are for the commit gate


def test_allow_from_config_reads_the_list_as_text(tmp_path):
    p = tmp_path / "_config.yml"
    p.write_text("public_safe:\n  allow:\n    - '@noaa.gov'   # derived addresses are public by construction\n")
    assert allow_from_config(p) == ["@noaa.gov"]
    assert allow_from_config(None) == [] and allow_from_config(tmp_path / "missing.yml") == []
    p.write_text("public_safe:\n  allow: nope\n")
    with pytest.raises(ValueError, match="list of strings"):
        allow_from_config(p)


def test_this_repository_is_public_safe():
    """`just public-safe` over the checkout, as CI runs it: with the frozen
    fixture's allow list, nothing tracked or untracked-but-not-ignored holds
    material that must not be public."""
    findings = scan_tree(REPO, allow_from_config(FIXTURE_CONFIG / "cfg" / "_config.yml"))
    assert findings == [], "\n".join(str(f) for f in findings)


def test_a_token_glued_to_a_word_still_fires_as_in_a_binary_plan():
    assert "jwt" in rules("binary" + JWT)


def test_the_finding_shows_only_the_head_of_a_value():
    f = scan_bytes(f'x = "{AKIA}"'.encode(), "a.tf")[0]
    assert isinstance(f, Finding) and f.excerpt == AKIA[:6] + "…" and AKIA not in str(f)
