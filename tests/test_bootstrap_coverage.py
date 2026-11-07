# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the bootstrap root makes, reads, adopts or leaves by hand, and says so.

Every declared S3 backend bound to a root gets its bucket made when absent
(one bucket set per backend, managed from then on); a backend bound to no
root is left out, with a line saying so; a bucket the account cannot be
asked about is refused, not guessed. A state bucket the bootstrap made stays
managed by the root through the second interview; one that stood before the
root is read and never managed. The GCP section makes the GCS state bucket
when absent with the same managed-or-read fork. The generated README
tabulates what the root covers (MADE, READ, ADOPTED, BY HAND) for every
section, the Okta section audits what it never makes, the write role
carries the read document as a second policy, and the release carries the
bootstrap modules.

history: bundle XII items 5 and 33, XX items 1 to 3.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from harness import module_path

from cs_image_system.base import bootstrap as bs
from cs_image_system.base.bootstrap.questions import COVERAGE_STATUSES
from tests.test_bootstrap import EXAMPLES, _assigned, _git, _starter_copy
from tests.test_bootstrap_aws import _account as _aws_account
from tests.test_bootstrap_aws import _facts, _filled

REPO = Path(__file__).resolve().parents[1]
ACCOUNT = "111122223333"


def _row(readme: str, section: str, resource: str, status: str) -> bool:
    """A row of the README's coverage table: `| <section> | ...<resource>... | <status> |`."""
    return re.search(rf"^\| {section} \| [^|]*{re.escape(resource)}[^|]* \| {status} \|", readme, flags=re.M) is not None


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
    """A probe answering per bucket NAME (the section asks about every
    declared bucket), and for the rest as the AWS tests' probe does."""
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
    assert _row(readme, "aws", "acme-tfstate-east1", "MADE"), readme
    assert _row(readme, "aws", "acme-tfstate-east2", "READ"), readme
    # the module: one bucket set per entry, and the WRITE role's StatePrefix statement covers each prefix
    module = (module_path("bootstrap_aws") / "main.tf").read_text()
    for needle in ('resource "aws_s3_bucket" "other"', 'resource "aws_s3_bucket_versioning" "other"',
                   'resource "aws_s3_bucket_server_side_encryption_configuration" "other"',
                   'resource "aws_s3_bucket_public_access_block" "other"', "for bucket, prefix in var.other_state_buckets"):
        assert needle in module, needle
    # the second interview keeps the answer: a bucket this root made never leaves the plan
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
    assert _row(readme, "aws", "acme-tfstate-east1", "BY HAND"), readme
    assert re.search(r"aws_other_state_buckets\s*=\s*\{\}", (bs.output_dir(root) / "bootstrap.auto.tfvars").read_text())


def test_a_bucket_the_account_cannot_be_asked_about_is_refused_not_guessed(tmp_path: Path):
    from cs_image_system.base.bootstrap.questions import Refused
    root = _complete_tree(tmp_path)
    facts = bs.gather(root, gh=False)
    facts.owner_id, facts.repo_id = 4242, 987654
    facts.probe = _account({"acme-tfstate-east2": True}, oidc=True, read=True, write=True, profile=True)   # east1 unaskable
    with pytest.raises(Refused, match="other_state_buckets"):
        bs.run_interview(bs.discover(), facts, quiet=True, only=["github", "aws"])


# ------------------------------------------------- a bucket the root made stays managed
def test_a_bucket_the_root_made_stays_managed_after_the_second_interview(tmp_path: Path):
    root = _starter_copy(tmp_path)
    _filled(root)
    first = _facts(root, _aws_account(oidc=False, read=False, write=False, bucket=False, profile=False))
    answers = bs.run_interview(bs.discover(), first, quiet=True, only=["github", "aws"])
    assert answers["aws"]["state_bucket_exists"] is False and answers["aws"]["state_bucket_managed"] is True
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    assert bs.regenerate(root)
    out = bs.output_dir(root)
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "aws_state_bucket_exists", "false") and _assigned(tfvars, "aws_state_bucket_managed", "true")
    assert "CREATED" in (out / "README.md").read_text()
    # the second interview, the bucket now standing: observed (no answer to pop), the backend binds,
    # and the bucket stays managed -- the four resources do not leave the plan
    second = _facts(root, _aws_account(oidc=True, read=True, write=True, bucket=True, profile=True))
    prior = bs.read_answers(root / bs.ANSWERS_FILE)
    again = bs.run_interview(bs.discover(), second, quiet=True, prior=prior, only=["github", "aws"])
    assert again["aws"]["state_bucket_exists"] is True and again["aws"]["state_bucket_managed"] is True
    bs.write_answers(root / bs.ANSWERS_FILE, again)
    assert bs.regenerate(root)
    assert 'backend "s3" {' in (out / "providers.tf").read_text()
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "aws_state_bucket_exists", "true") and _assigned(tfvars, "aws_state_bucket_managed", "true")
    assert "MANAGED" in (out / "README.md").read_text()
    # a bucket that stood before the root is read and never managed
    theirs = _starter_copy(tmp_path / "theirs")
    _filled(theirs)
    a = bs.run_interview(bs.discover(), _facts(theirs, _aws_account(oidc=True, read=True, write=True, bucket=True, profile=True)),
                         quiet=True, only=["github", "aws"])["aws"]
    assert a["state_bucket_exists"] is True and a["state_bucket_managed"] is False
    bs.write_answers(theirs / bs.ANSWERS_FILE, {"aws": a, "github": {"wanted": False}})
    assert bs.regenerate(theirs)
    tfvars = (bs.output_dir(theirs) / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "aws_state_bucket_managed", "false")
    assert "not managed" in (bs.output_dir(theirs) / "README.md").read_text()
    # the module counts the bucket resources on `managed`, never on `exists`
    for path in [module_path("bootstrap_aws") / "main.tf"]:
        module = path.read_text()
        assert module.count("var.state_bucket_managed ? 1 : 0") == 4 and "state_bucket_exists ? 0 : 1" not in module, path


# --------------------------------------------------------------- the GCS bucket
def _gce_root(tmp_path: Path, bucket_exists: bool) -> tuple[Path, Path]:
    from tests.test_bootstrap_gcp import _facts as _gcp_facts
    from tests.test_bootstrap_gcp import _project, _tree
    root = _tree(tmp_path)
    facts = _gcp_facts(root, _project(None, number=True, pool=False, provider=False, read=False, write=False, bucket=bucket_exists))
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
    assert "us-east1" in readme and _row(readme, "gcp", "acme-gcs-tfstate", "MADE"), readme
    module = (module_path("bootstrap_gcp") / "main.tf").read_text()
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
    assert _row((out / "README.md").read_text(), "gcp", "acme-gcs-tfstate", "READ")


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
    assert "BY HAND" in (REPO / "docs" / "OPERATIONS.md").read_text()      # the standing audit in the docs


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


# ------------------------------------------------------------- the roles and the modules
def test_the_write_role_carries_the_read_document():
    for path in [module_path("bootstrap_aws") / "main.tf"]:
        module = path.read_text()
        assert module.count("local.read_document") == 2, path                      # on both roles
        assert 'resource "aws_iam_role_policy" "write_reads"' in module and '"cs-image-system-write-reads"' in module, path
        assert module.count('"StorageReality"') == 1 and module.count('"Describe"') == 1   # one document, defined once
    guide = (EXAMPLES / "_skeleton" / "CI_SETUP.md").read_text()
    assert "cs-image-system-write-reads" in guide and "REFUSED" in guide


def test_the_release_carries_the_bootstrap_modules():
    for module in ("bootstrap_aws", "bootstrap_gcp"):
        assert [f.name for f in sorted(module_path(module).glob("*.tf"))] == ["main.tf", "outputs.tf", "variables.tf"], module
    assert shutil.which("git") and _git is not None
