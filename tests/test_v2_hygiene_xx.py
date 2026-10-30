# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene bundle XX (stage 104): the bootstrap produces a working set for
every underlying resource a tree declares, and says what it does not.

1. Every declared S3 backend bound to a root gets its bucket made when
   absent (one bucket set per backend, managed from then on); a backend
   bound to no root is left out, with a line saying so.
2. The GCP section makes the GCS state bucket when absent (versioned,
   uniform access, no public access; the CI identities' object access
   added), with the managed-or-read fork the AWS section has.
3. The generated README tabulates what the root covers: MADE, READ,
   ADOPTED or BY HAND with the reason, for every section.
4. (b) `validate` prints the modification tests' stand-in per OS builder;
   (c) it WARNS when a query plainly names another family than the token.
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import yaml

from cs_image_system.base import bootstrap as bs
from cs_image_system.base.bootstrap.questions import COVERAGE_STATUSES

from tests.test_v2_bootstrap import EXAMPLES, _assigned, _git, _starter_copy
from v2_support import copy_config, load_context, reset_singletons, stub_environment

REPO = Path(__file__).resolve().parents[1]
ACCOUNT = "111122223333"


# ------------------------------------------------------------- the AWS buckets
def _complete_tree(tmp_path: Path) -> Path:
    """The complete starter with a team's values: TWO S3 backends, `s3-east2`
    the default, `s3-east1` bound by the storage builders and a runtime."""
    root = _starter_copy(tmp_path, "complete")
    for name in ("runtime-builders.yml", "state-backends.yml", "state-backends-2.yml"):
        f = root / "cfg" / name
        f.write_text(f.read_text().replace('"123456789012"', f'"{ACCOUNT}"').replace("REPLACE-ME-profile", "acme")
                     .replace("tfstate-REPLACE-ME-east2", "acme-tfstate-east2").replace("tfstate-REPLACE-ME-east1", "acme-tfstate-east1")
                     .replace("REPLACE-ME-ssm-profile", "acme-ssm").replace("REPLACE-ME-bake-profile", "acme-bake"))
    return root


def _account(buckets: dict[str, bool], **present: bool):
    """A probe answering per bucket NAME (hygiene XX: the section asks about
    every declared bucket), and for the rest as the AWS tests' probe does."""
    def probe(args: list[str], timeout: int = 60) -> tuple[int, str]:
        text = " ".join(args)
        if "head-bucket" in text:
            bucket = args[args.index("--bucket") + 1]
            if bucket not in buckets:
                return 255, "Unable to locate credentials."
            return (0, "{}") if buckets[bucket] else (254, "An error occurred (404) when calling the HeadBucket operation: Not Found")
        key = "oidc" if "get-open-id-connect-provider" in text else "read" if "get-role" in text and "readonly" in text \
            else "write" if "get-role" in text else "profile" if "get-instance-profile" in text else None
        if key is None or key not in present:
            return 255, "Unable to locate credentials."
        return (0, "{}") if present[key] else (254, "NoSuchEntity")
    return probe


def _aws_root(tmp_path: Path, buckets: dict[str, bool]) -> tuple[Path, Path, dict]:
    root = _complete_tree(tmp_path)
    facts = bs.gather(root, gh=False)
    facts.owner_id, facts.repo_id = 4242, 987654
    facts.probe = _account(buckets, oidc=True, read=True, write=True, profile=True)
    answers = bs.run_interview(bs.discover(), facts, quiet=True, only=["github", "aws"])
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    assert bs.regenerate(root)
    return root, bs.output_dir(root), answers


def test_the_facts_know_which_backends_a_root_is_bound_to(tmp_path: Path):
    from cs_image_system.base.bootstrap.facts import bound_backend_names, other_state_backends
    facts = bs.gather(_complete_tree(tmp_path), gh=False)
    assert [b["name"] for b in other_state_backends(facts, "s3")] == ["s3-east1"]
    assert bound_backend_names(facts) >= {"s3-east2", "s3-east1", "local-dev"}


def test_a_second_s3_backends_bucket_is_made_when_bound_and_absent(tmp_path: Path):
    root, out, answers = _aws_root(tmp_path, {"acme-tfstate-east2": True, "acme-tfstate-east1": False})
    assert answers["aws"]["other_state_buckets"] == "acme-tfstate-east1=statefiles/complete-example"
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    assert re.search(r'aws_other_state_buckets\s*=\s*\{\n\s*"acme-tfstate-east1"\s*=\s*"statefiles/complete-example"\n\s*\}', tfvars), tfvars
    assert _assigned((out / "main.tf").read_text(), "other_state_buckets", "var.aws_other_state_buckets")
    readme = (out / "README.md").read_text()
    assert "the S3 backend's bucket `acme-tfstate-east1` (prefix `statefiles/complete-example`) is CREATED here" in readme
    assert "| aws | the S3 backend `s3-east1`'s bucket `acme-tfstate-east1` | MADE |" in readme
    assert "| aws | the default S3 backend's bucket `acme-tfstate-east2` | READ |" in readme
    # the module: one bucket set per entry, and the WRITE role's StatePrefix statement covers each prefix
    module = (REPO / "tfmodules" / "bootstrap_aws" / "main.tf").read_text()
    for needle in ('resource "aws_s3_bucket" "other"', 'resource "aws_s3_bucket_versioning" "other"',
                   'resource "aws_s3_bucket_server_side_encryption_configuration" "other"',
                   'resource "aws_s3_bucket_public_access_block" "other"', "for bucket, prefix in var.other_state_buckets"):
        assert needle in module, needle
    # the second interview keeps the answer: a bucket this root made never leaves the plan (the hygiene XII item 5 rule)
    facts = bs.gather(root, gh=False)
    facts.owner_id, facts.repo_id = 4242, 987654
    facts.probe = _account({"acme-tfstate-east2": True, "acme-tfstate-east1": True}, oidc=True, read=True, write=True, profile=True)
    again = bs.run_interview(bs.discover(), facts, quiet=True, prior=bs.read_answers(root / bs.ANSWERS_FILE), only=["github", "aws"])
    assert again["aws"]["other_state_buckets"] == "acme-tfstate-east1=statefiles/complete-example"


def test_a_backend_bound_to_no_root_is_left_out_with_a_line_saying_so(tmp_path: Path):
    root = _complete_tree(tmp_path)
    # unbind s3-east1: every root that named it now names the default
    for name in ("storage-builders.yml", "runtime-builders.yml"):
        f = root / "cfg" / name
        f.write_text(f.read_text().replace("state_configuration: s3-east1", "state_configuration: default"))
    facts = bs.gather(root, gh=False)
    facts.owner_id, facts.repo_id = 4242, 987654
    facts.probe = _account({"acme-tfstate-east2": True, "acme-tfstate-east1": False}, oidc=True, read=True, write=True, profile=True)
    answers = bs.run_interview(bs.discover(), facts, quiet=True, only=["github", "aws"])
    assert answers["aws"]["other_state_buckets"] == ""
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    assert bs.regenerate(root)
    readme = (bs.output_dir(root) / "README.md").read_text()
    assert ("| aws | the S3 backend `s3-east1`'s bucket `acme-tfstate-east1` | BY HAND | declared but bound to no root, "
            "so nothing would use it: not made; bind a root to it and re-run the interview, or drop the backend |") in readme
    assert re.search(r"aws_other_state_buckets\s*=\s*\{\}", (bs.output_dir(root) / "bootstrap.auto.tfvars").read_text())


def test_a_bucket_the_account_cannot_be_asked_about_is_refused_not_guessed(tmp_path: Path):
    import pytest
    from cs_image_system.base.bootstrap.questions import Refused
    root = _complete_tree(tmp_path)
    facts = bs.gather(root, gh=False)
    facts.owner_id, facts.repo_id = 4242, 987654
    facts.probe = _account({"acme-tfstate-east2": True}, oidc=True, read=True, write=True, profile=True)   # east1 unaskable
    with pytest.raises(Refused, match="other_state_buckets"):
        bs.run_interview(bs.discover(), facts, quiet=True, only=["github", "aws"])


# --------------------------------------------------------------- the GCS bucket
def _gce_root(tmp_path: Path, bucket_exists: bool) -> tuple[Path, Path]:
    from tests.test_v2_bootstrap_gcp import _facts, _project, _tree
    root = _tree(tmp_path)
    facts = _facts(root, _project(None, number=True, pool=False, provider=False, read=False, write=False, bucket=bucket_exists))
    answers = bs.run_interview(bs.discover(), facts, quiet=True, only=["github", "gcp"])
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    assert bs.regenerate(root)
    return root, bs.output_dir(root)


def test_the_gcs_state_bucket_is_made_when_absent_and_read_when_it_stands(tmp_path: Path):
    root, out = _gce_root(tmp_path, bucket_exists=False)
    answers = bs.read_answers(root / bs.ANSWERS_FILE)["gcp"]
    assert answers["state_bucket_exists"] is False and answers["state_bucket_managed"] is True
    assert answers["state_bucket_location"] == "us-east1"                     # the runtime's zone's region
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    for key, value in (("gcp_state_bucket", '"acme-gcs-tfstate"'), ("gcp_state_bucket_managed", "true"),
                       ("gcp_state_bucket_exists", "false"), ("gcp_state_bucket_location", '"us-east1"'),
                       ("gcp_state_prefix", '"statefiles/my-team-images"')):
        assert _assigned(tfvars, key, value), key
    assert 'backend "local" {}' in (out / "providers.tf").read_text()        # local first, as on AWS
    readme = (out / "README.md").read_text()
    assert "is CREATED here in us-east1 (versioned, uniform access, no public access" in readme
    assert "| gcp | the GCS state bucket `acme-gcs-tfstate` | MADE |" in readme
    module = (REPO / "tfmodules" / "bootstrap_gcp" / "main.tf").read_text()
    for needle in ('resource "google_storage_bucket" "state"', "uniform_bucket_level_access = true",
                   'public_access_prevention    = "enforced"', 'resource "google_storage_bucket_iam_member" "state_read"',
                   'resource "google_storage_bucket_iam_member" "state_write"', "roles/storage.objectViewer"):
        assert needle in module, needle
    assert not re.search(r"google_storage_bucket_iam_(binding|policy)\b", module)   # single members, never authoritative
    # the bucket stands: read, never managed; the root binds to it
    root, out = _gce_root(tmp_path / "b", bucket_exists=True)
    answers = bs.read_answers(root / bs.ANSWERS_FILE)["gcp"]
    assert answers["state_bucket_exists"] is True and answers["state_bucket_managed"] is False
    assert 'backend "gcs" {' in (out / "providers.tf").read_text()
    assert "| gcp | the GCS state bucket `acme-gcs-tfstate` | READ | stood before this root: read, never managed |" in (out / "README.md").read_text()


# ------------------------------------------------------------- the audit table
def test_every_sections_coverage_is_a_table_in_the_readme_in_the_audits_words(tmp_path: Path):
    root, out, _ = _aws_root(tmp_path, {"acme-tfstate-east2": True, "acme-tfstate-east1": True})
    readme = (out / "README.md").read_text()
    assert "## What this root covers" in readme
    table = readme[readme.index("## What this root covers"):readme.index("## Apply")]
    rows = re.findall(r"^\| (\w+) \| (.+?) \| (MADE|READ|ADOPTED|BY HAND) \| (.+?) \|$", table, flags=re.M)
    assert {r[0] for r in rows} == {"aws", "github"}
    assert all(r[2] in COVERAGE_STATUSES and r[3].strip() for r in rows), rows      # every row has a status and a reason
    by_hand = [r[1] for r in rows if r[2] == "BY HAND"]
    assert any("network" in r for r in by_hand) and any("secrets" in r for r in by_hand)
    assert any(r[1].startswith("the READ role") and r[2] == "ADOPTED" for r in rows)
    # the sections every starter wants carry an audit: no section is silent
    for name, section in {s.name: s for s in bs.discover()}.items():
        assert section.render is not None, name
    assert (REPO / "docs" / "OPERATIONS.md").read_text().count("| BY HAND |") >= 4   # the standing audit in the docs


def test_the_okta_section_audits_what_it_never_makes():
    from cs_image_system.okta_opa_plugin.bootstrap import render
    rendered = render({"workload_connection": "github-widgets", "workload_role": "widgets-ci", "team": "acme",
                       "api_host": "acme.pam.okta.com", "production_branch": "main", "connection_exists": True,
                       "connection_active": False, "connection_requires_repository": True, "role_exists": False,
                       "role_bound": False, "role_pinned": False, "builder_names_them": False, "okta_app_authenticates": True,
                       "okta_app_read_only": True, "okta_app_readable": False})
    statuses = {res: status for res, status, _ in rendered.coverage}
    assert statuses["the OPA workload connection `github-widgets`"] == "BY HAND"
    assert statuses["the OPA service user and its key pair"] == "BY HAND"
    assert all(why for _, _, why in rendered.coverage)


# -------------------------------------------------------- validate: items 4(b) and 4(c)
def _edit_os_builders(root: Path, change) -> None:
    p = root / "cfg" / "os-builders.yml"
    doc = yaml.safe_load(p.read_text())
    change(doc["os_builders"])
    p.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_validate_prints_the_stand_in_per_os_builder_and_warns_on_a_query_naming_another_family(tmp_path, monkeypatch, caplog):
    from cs_image_system.base.commands.validate import check_image_sources, family_named_by_query
    from cs_image_system.contract.image import ImageQuery
    assert family_named_by_query(ImageQuery(name="AlmaLinux OS 10*x86_64*")) == "alma-linux"
    assert family_named_by_query(ImageQuery(family="rhel-10")) == "rhel"
    assert family_named_by_query(ImageQuery(name="my-golden-*")) is None
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)

    def change(entries):
        # the reference's shape before bundle XX item 4(d): family rhel, an Alma query
        rh = next(e for e in entries if e["name"] == "basic-rh-10")
        rh["family"] = "rhel"
        next(r for r in rh["runtimes"] if r["name"] == "aws-my-rhel8")["query"] = {
            "name": "AlmaLinux OS 10*x86_64", "publisher": ["764336703387"]}
    _edit_os_builders(root, change)
    ctx = load_context(root)
    try:
        with caplog.at_level(logging.INFO, logger="cs_image_system.base.commands.validate"):
            assert check_image_sources(ctx) == []
    finally:
        reset_singletons()
    messages = [r.getMessage() for r in caplog.records]
    stand_ins = [m for m in messages if m.startswith("mod-test stand-in:")]
    assert len(stand_ins) == 3, stand_ins
    assert "mod-test stand-in: OS builder 'basic-rh-10': almalinux:10 (the catalog's docker block for 'rhel')" in stand_ins
    assert "mod-test stand-in: OS builder 'my-deb-12': debian:12 (the catalog's docker block for 'debian')" in stand_ins
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and "names 'alma-linux'" in r.getMessage()]
    assert len(warnings) == 1 and "under family 'rhel'" in warnings[0] and "`family: alma-linux`" in warnings[0], warnings


def test_a_family_that_says_what_the_image_is_draws_no_warning(tmp_path, monkeypatch, caplog):
    from cs_image_system.base.commands.validate import check_image_sources
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))                                  # the fixture: alma-linux, the catalog's query
    try:
        with caplog.at_level(logging.INFO, logger="cs_image_system.base.commands.validate"):
            assert check_image_sources(ctx) == []
    finally:
        reset_singletons()
    assert not [r for r in caplog.records if r.levelno == logging.WARNING and "names" in r.getMessage()]


def test_the_starters_carry_the_modules_byte_for_byte():
    for name in ("standard-aws", "standard-gce", "complete", "standard-aws-posix"):
        for module in ("bootstrap_aws", "bootstrap_gcp"):
            for f in (REPO / "tfmodules" / module).glob("*.tf"):
                assert (EXAMPLES / name / "tfmodules" / module / f.name).read_bytes() == f.read_bytes(), (name, module, f.name)
    assert shutil.which("git") and _git is not None
