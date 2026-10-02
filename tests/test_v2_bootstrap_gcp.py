# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 70 step 5: the GCP section of the bootstrap -- contributed by the
gcloud plugin through the entry-point group; every "existing" question a probe
through ``gcloud`` (refused by name under --quiet when the project cannot be
asked; a starter's placeholders are no defaults); what exists READ, never
managed (a shared provider's condition is kept verbatim and never rewritten);
every role and binding one member added; the three GCP secrets set from the
applied root's outputs; the root bound to the tree's GCS bucket when it stands.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_v2_bootstrap import EXAMPLES, REPO, TREES, _assigned, _starter_copy

from cs_image_system.base import bootstrap as bs
from cs_image_system.base.bootstrap.questions import Refused
from cs_image_system.gcloud_runtime import bootstrap as gcp

PROJECT = "acme-proj"
NUMBER = "424242424242"
GUIDE_MAPPING = {"google.subject": "assertion.sub", "attribute.repository": "assertion.repository",
                 "attribute.repository_id": "assertion.repository_id", "attribute.ref": "assertion.ref"}


def _tree(tmp_path: Path, filled: bool = True) -> Path:
    root = _starter_copy(tmp_path, "standard-gce")
    if filled:
        for name in ("runtime-builders.yml", "state-backends.yml"):
            f = root / "cfg" / name
            f.write_text(f.read_text().replace("my-project-REPLACE-ME", PROJECT).replace("tfstate-REPLACE-ME", "acme-gcs-tfstate"))
    return root


def _project(record: dict | None = None, **present: bool):
    """A probe that answers for the project: number, pool, provider, read,
    write and bucket are each present, absent (gcloud's NOT_FOUND) or, when
    not named, unaskable (no credentials). ``record`` is what an existing
    provider describes itself with."""
    calls: list[list[str]] = []

    def probe(args: list[str], timeout: int = 60) -> tuple[int, str]:
        calls.append(args)
        text = " ".join(args)
        if "projects describe" in text:
            key, found = "number", NUMBER
        elif "providers describe" in text:
            key, found = "provider", json.dumps(record or {})
        elif "workload-identity-pools describe" in text:
            key, found = "pool", "{}"
        elif "service-accounts describe" in text:
            key, found = ("read" if "readonly" in text else "write"), "{}"
        elif "buckets describe" in text:
            key, found = "bucket", "{}"
        else:
            key, found = None, ""
        if key is None or key not in present:
            return 1, "ERROR: (gcloud.auth) You do not currently have an active account selected."
        return (0, found) if present[key] else (1, f"ERROR: NOT_FOUND: Requested entity was not found ({key}).")
    probe.calls = calls                                        # type: ignore[attr-defined]
    return probe


def _facts(root: Path, probe=None, ids: bool = True):
    facts = bs.gather(root, gh=False)
    if ids:
        facts.owner_id, facts.repo_id = 4242, 987654
    if probe is not None:
        facts.probe = probe
    return facts


def _section():
    return next(s for s in bs.discover() if s.name == "gcp")


FRESH = dict(number=True, pool=False, provider=False, read=False, write=False, bucket=True)


# ------------------------------------------------------------- the section itself

def test_the_gcloud_plugin_contributes_the_section_and_the_tree_decides(tmp_path: Path):
    assert [s.name for s in bs.discover()] == ["github", "aws", "gcp"]       # GitHub first, then the plugins' by name
    gce = bs.gather(_tree(tmp_path), gh=False)
    assert _section().wanted_default(gce) is True
    aws_section = next(s for s in bs.discover() if s.name == "aws")
    assert aws_section.wanted_default(gce) is False                           # a GCE-only tree does not want AWS
    other = tmp_path / "aws"
    shutil.copytree(EXAMPLES / "standard-aws", other)
    assert _section().wanted_default(bs.gather(other, git=False, gh=False)) is False
    # so a quiet interview over a GCE tree asks GitHub and GCP and never refuses on an AWS question
    out = bs.run_interview(bs.discover(), _facts(_tree(tmp_path / "again"), _project(None, **FRESH)), quiet=True)
    assert out["aws"] == {"wanted": False} and out["gcp"]["wanted"] and out["github"]["wanted"]


def test_placeholders_and_a_project_that_cannot_be_asked_are_refused_by_name(tmp_path: Path):
    raw = _tree(tmp_path, filled=False)
    with pytest.raises(Refused, match=r"gcp\.project: The GCP project id -- no default can be derived"):
        bs.run_interview([_section()], _facts(raw, _project(None, **FRESH)), quiet=True)
    root = _tree(tmp_path / "filled")
    with pytest.raises(Refused, match=r"gcp\.project_number: .* \(the project could not be asked: `gcloud` is absent or has no credentials\)"):
        bs.run_interview([_section()], _facts(root, _project()), quiet=True)


def test_a_fresh_project_gets_the_guides_pool_provider_and_accounts(tmp_path: Path):
    root = _tree(tmp_path)
    probe = _project(None, **FRESH)
    a = bs.run_interview([_section()], _facts(root, probe), quiet=True)["gcp"]
    assert (a["project"], a["project_number"], a["repository"]) == (PROJECT, NUMBER, "acme/widgets")
    assert (a["pool"], a["pool_exists"], a["provider"], a["provider_exists"]) == ("github", False, "github", False)
    assert a["principal_attribute"] == "repository_id" and a["repo_id"] == "987654"
    assert a["attribute_condition"] == "assertion.repository_id == '987654'"   # this repository and nothing else
    assert a["read_account"] == "csis-github-readonly" and a["read_account_exists"] is False
    assert a["want_write"] is True and a["write_account"] == "csis-github-apply"   # the tree's default runtime is GCE
    assert a["state_bucket"] == "acme-gcs-tfstate" and a["state_bucket_exists"] is True
    # no provider is asked for in a pool that does not exist
    assert not any("providers describe" in " ".join(c) for c in probe.calls)
    # without the id, the name is what the bindings and the condition use, and the id is not asked
    b = bs.run_interview([_section()], _facts(root, _project(None, **FRESH), ids=False), quiet=True)["gcp"]
    assert b["principal_attribute"] == "repository" and "repo_id" not in b
    assert b["attribute_condition"] == "assertion.repository == 'acme/widgets'"


def test_an_existing_provider_is_read_as_it_stands_and_decides_the_attribute(tmp_path: Path):
    """A provider other repositories share: its condition is kept verbatim and
    never rewritten, and the bindings name an attribute it actually maps."""
    root = _tree(tmp_path)
    shared = {"attributeCondition": "assertion.repository in ['acme/other', 'acme/widgets']",
              "attributeMapping": {"google.subject": "assertion.sub", "attribute.repository": "assertion.repository"}}
    probe = _project(shared, number=True, pool=True, provider=True, read=True, write=True, bucket=True)
    a = bs.run_interview([_section()], _facts(root, probe), quiet=True)["gcp"]
    assert a["pool_exists"] and a["provider_exists"] and a["read_account_exists"]
    assert a["attribute_condition"] == shared["attributeCondition"]
    assert a["principal_attribute"] == "repository" and "repo_id" not in a     # it maps no repository_id
    assert gcp.names_repository(a["attribute_condition"], a)
    # one that maps the id lets the bindings use it
    mapped = {**shared, "attributeMapping": GUIDE_MAPPING}
    c = bs.run_interview([_section()], _facts(root, _project(mapped, number=True, pool=True, provider=True,
                                                             read=True, write=True, bucket=True)), quiet=True)["gcp"]
    assert c["principal_attribute"] == "repository_id" and c["repo_id"] == "987654"


# ----------------------------------------------------------------- the root it makes

def _root(tmp_path: Path, record: dict | None = None, want_write: bool | None = None, **present: bool) -> tuple[Path, Path]:
    root = _tree(tmp_path)
    answers = bs.run_interview(bs.discover(), _facts(root, _project(record, **present)), quiet=True)
    if want_write is not None:
        answers["gcp"]["want_write"] = want_write
        for k in ("write_account", "write_account_exists", "write_roles"):
            if not want_write:
                answers["gcp"].pop(k, None)
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    assert bs.regenerate(root)
    return root, bs.output_dir(root)


def test_the_root_reads_what_exists_adds_single_members_and_sets_the_secrets_from_outputs(tmp_path: Path):
    root, out = _root(tmp_path, None, None, **FRESH)
    main = (out / "main.tf").read_text()
    assert 'module "bootstrap_gcp"' in main and 'module "bootstrap_github"' in main and "bootstrap_aws" not in main
    assert _assigned(main, "source", '"../../tfmodules/bootstrap_gcp"')
    providers = (out / "providers.tf").read_text()
    assert 'source  = "hashicorp/google"' in providers and 'provider "google" {' in providers
    assert 'backend "gcs" {' in providers and _assigned(providers, "bucket", '"acme-gcs-tfstate"')   # decision D8, in GCS
    assert _assigned(providers, "prefix", '"statefiles/my-team-images/bootstrap"')
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    for key, value in (("gcp_project", f'"{PROJECT}"'), ("gcp_project_number", f'"{NUMBER}"'),
                       ("gcp_pool_exists", "false"), ("gcp_provider_exists", "false"), ("gcp_want_write", "true"),
                       ("gcp_principal_attribute", '"repository_id"'), ("gcp_principal_value", '"987654"'),
                       ("gcp_attribute_condition", '"assertion.repository_id == \'987654\'"')):
        assert _assigned(tfvars, key, value), key
    assert '"roles/compute.viewer"' in tfvars and '"roles/iam.serviceAccountUser"' in tfvars
    script = (out / "set-secrets.sh").read_text()
    for secret, output in (("GCP_WORKLOAD_IDENTITY_PROVIDER", "gcp_workload_identity_provider"),
                           ("GCP_SERVICE_ACCOUNT", "gcp_read_service_account"),
                           ("GCP_APPLY_SERVICE_ACCOUNT", "gcp_write_service_account")):
        assert f"from_output {secret} {output}" in script and f"from_file {secret}" not in script
    assert "from_file CSIS_CONFIG_IDENTITY" in script                        # the rest still from files
    # the README says who terraform acts as: the identities the interview asked as, not whatever ADC happens to be
    readme = (out / "README.md").read_text()
    assert "export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)" in readme
    assert "export GITHUB_TOKEN=$(gh auth token)" in readme
    assert readme.index("export GOOGLE_OAUTH_ACCESS_TOKEN") < readme.index("tofu init")
    assert "application-default" in readme and "can read no IAM" in readme
    # and the guide sends people to those lines instead of listing bare commands
    guide = (EXAMPLES / "complete" / "CI_SETUP.md").read_text()
    section = guide[guide.index("### 3.0 The bootstrap"):guide.index("### 3.1 ")]
    assert "GOOGLE_OAUTH_ACCESS_TOKEN" in section and "export" in section and '"Apply" block' in section
    assert section.index("GOOGLE_OAUTH_ACCESS_TOKEN") < section.index("tofu init && tofu plan && tofu apply")
    # the module: reads what exists, and every grant is one member added -- nothing authoritative
    module = (REPO / "tfmodules" / "bootstrap_gcp" / "main.tf").read_text()
    for needle in ('data "google_iam_workload_identity_pool" "github"', 'data "google_iam_workload_identity_pool_provider" "github"',
                   'data "google_service_account" "read"', "google_project_iam_member", "google_service_account_iam_member",
                   '"attribute.repository_id" = "assertion.repository_id"', "attribute.ref/refs/heads/${var.production_branch}",
                   "https://token.actions.githubusercontent.com", "roles/iam.workloadIdentityUser"):
        assert needle in module, needle
    assert not re.search(r"google_\w+_iam_(binding|policy)\b", module)        # authoritative forms would replace other members
    guide = (EXAMPLES / "complete" / "CI_SETUP.md").read_text()
    section = guide[guide.index("### 3.4 GCP"):guide.index("### 3.5 ")]
    for mapped in GUIDE_MAPPING:
        assert mapped in section and mapped in module, mapped                  # the module's mapping is the guide's
    for name in TREES:
        assert (EXAMPLES / name / "tfmodules" / "bootstrap_gcp" / "main.tf").read_bytes() == (REPO / "tfmodules" / "bootstrap_gcp" / "main.tf").read_bytes()


def test_a_shared_provider_that_does_not_name_this_repository_is_a_step_by_hand_not_a_rewrite(tmp_path: Path):
    theirs = {"attributeCondition": "assertion.repository == 'acme/other'", "attributeMapping": GUIDE_MAPPING}
    root, out = _root(tmp_path, theirs, False, number=True, pool=True, provider=True, read=True, write=True, bucket=False)
    readme = (out / "README.md").read_text()
    assert "does not name this repository (`acme/widgets`, id 987654)" in readme
    assert "never rewrites a provider that exists" in readme
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "gcp_provider_exists", "true") and _assigned(tfvars, "gcp_want_write", "false")
    assert _assigned(tfvars, "gcp_write_account", '""') and re.search(r"gcp_write_roles\s*=\s*\[\]", tfvars)
    assert "No WRITE service account: `GCP_APPLY_SERVICE_ACCOUNT` is set to the READ-ONLY account's" in readme
    assert 'backend "local" {}' in (out / "providers.tf").read_text()        # the bucket does not stand: local first


@pytest.mark.skipif(shutil.which("tofu") is None, reason="tofu not installed")
def test_the_root_validates_with_tofu(tmp_path: Path):
    from tests.test_v2_gcp_increment3 import private_plugin_cache
    root, out = _root(tmp_path, None, None, **FRESH)
    env = {**os.environ, "TF_PLUGIN_CACHE_DIR": str(private_plugin_cache(tmp_path, [out, REPO / "tfmodules" / "bootstrap_gcp"]))}
    for args in (["init", "-backend=false", "-input=false", "-no-color"], ["validate", "-no-color"]):
        res = subprocess.run(["tofu", *args], cwd=out, capture_output=True, text=True, timeout=600, env=env)
        assert res.returncode == 0, f"tofu {args[0]}\n{res.stdout}\n{res.stderr}"
