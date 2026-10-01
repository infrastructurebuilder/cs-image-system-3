# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 70 step 4: the AWS section of the bootstrap -- contributed by the AWS
plugin through the entry-point group; every "existing" question a fork whose
default is a probe of the account (refused by name under --quiet when the
account cannot be asked, and a starter's placeholders are no defaults); roles
that exist adopted by import; the root's state bound to the tree's declared
bucket when it stands (decision D8), local when the bootstrap makes it; the
two role ARNs set as secrets from the applied root's outputs.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_v2_bootstrap import EXAMPLES, REPO, TREES, _assigned, _starter_copy

from cs_image_system.aws_runtime import bootstrap as aws
from cs_image_system.base import bootstrap as bs
from cs_image_system.base.bootstrap.facts import default_state_backend, is_placeholder, real, runtime_of_type
from cs_image_system.base.bootstrap.questions import Refused

ACCOUNT = "111122223333"


def _filled(root: Path) -> None:
    """The starter with a team's values where its placeholders were."""
    rt = root / "cfg" / "runtime-builders.yml"
    rt.write_text(rt.read_text().replace('"123456789012"', f'"{ACCOUNT}"').replace("REPLACE-ME-profile", "acme")
                  .replace("REPLACE-ME-ssm-instance-profile", "acme-ssm"))
    sb = root / "cfg" / "state-backends.yml"
    sb.write_text(sb.read_text().replace("tfstate-REPLACE-ME", "acme-tfstate").replace("REPLACE-ME-profile", "acme"))


def _account(**present: bool):
    """A probe that answers for the account: each of oidc, read, write, bucket,
    profile is present (exit 0), absent (the service's own not-found word) or,
    when not named at all, unaskable (no credentials)."""
    calls: list[list[str]] = []

    def probe(args: list[str], timeout: int = 60) -> tuple[int, str]:
        calls.append(args)
        text = " ".join(args)
        key, absent = None, "NoSuchEntity"
        if "get-open-id-connect-provider" in text:
            key = "oidc"
        elif "get-role" in text:
            key = "read" if "readonly" in text else "write"
        elif "head-bucket" in text:
            key, absent = "bucket", "An error occurred (404) when calling the HeadBucket operation: Not Found"
        elif "get-instance-profile" in text:
            key = "profile"
        if key is None or key not in present:
            return 255, "Unable to locate credentials. You can configure credentials by running \"aws configure\"."
        return (0, "{}") if present[key] else (254, absent)
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
    return next(s for s in bs.discover() if s.name == "aws")


# ------------------------------------------------------------- the section itself

def test_the_aws_plugin_contributes_the_section_and_the_tree_decides_whether_it_is_wanted(tmp_path: Path):
    assert [s.name for s in bs.discover()][:2] == ["github", "aws"]          # GitHub first, then the plugins' by name
    aws_tree = _starter_copy(tmp_path)
    assert _section().wanted_default(bs.gather(aws_tree, gh=False)) is True
    other = tmp_path / "gce"
    shutil.copytree(EXAMPLES / "standard-gce", other)
    facts = bs.gather(other, git=False, gh=False)
    uses_aws = runtime_of_type(facts, "aws") is not None or default_state_backend(facts, "s3") is not None
    assert _section().wanted_default(facts) is uses_aws                       # the gate asks the tree, not a constant
    assert aws.parse_tags("Project=acme, Environment=dev,broken,=x") == {"Project": "acme", "Environment": "dev"}
    assert is_placeholder("tfstate-REPLACE-ME") and is_placeholder("123456789012") and is_placeholder("")
    assert real(" acme ") == "acme" and real("REPLACE-ME-profile") is None


def test_a_starters_placeholders_are_no_defaults_and_quiet_refuses_them_by_name(tmp_path: Path):
    root = _starter_copy(tmp_path)
    with pytest.raises(Refused, match=r"aws\.account_id: The AWS account id -- no default can be derived"):
        bs.run_interview([_section()], _facts(root, _account()), quiet=True)


def test_an_account_that_cannot_be_asked_is_refused_not_guessed(tmp_path: Path):
    root = _starter_copy(tmp_path)
    _filled(root)
    with pytest.raises(Refused, match=r"aws\.oidc_provider_exists: .* -- no default can be derived \(the account could "
                                      r"not be asked: no AWS session, or `aws` is not installed\)"):
        bs.run_interview([_section()], _facts(root, _account()), quiet=True)   # the probe has no credentials


def test_the_forks_follow_the_account_and_the_subject_forms_follow_the_ids(tmp_path: Path):
    root = _starter_copy(tmp_path)
    _filled(root)
    probe = _account(oidc=True, read=True, write=False, bucket=True, profile=False)
    a = bs.run_interview([_section()], _facts(root, probe), quiet=True)["aws"]
    assert a["wanted"] and a["account_id"] == ACCOUNT and a["profile"] == "acme" and a["repository"] == "acme/widgets"
    assert (a["oidc_provider_exists"], a["read_role_exists"], a["write_role_exists"]) == (True, True, False)
    assert (a["state_bucket_exists"], a["instance_profile_exists"]) == (True, False)
    assert a["state_bucket"] == "acme-tfstate" and a["state_prefix"] == "statefiles/my-team-images"   # no trailing slash
    assert a["instance_profile"] == "acme-ssm" and a["subject_forms"] == "both"
    assert (a["owner_id"], a["repo_id"]) == ("4242", "987654")
    assert all("--profile" in c and "acme" in c for c in probe.calls)        # the probes ask as the tree's profile
    # without the ids the plain form alone is trusted, and the id questions are not asked at all
    b = bs.run_interview([_section()], _facts(root, probe, ids=False), quiet=True)["aws"]
    assert b["subject_forms"] == "plain" and "owner_id" not in b and "repo_id" not in b


def test_the_defaults_look_in_every_cfg_file_as_the_loader_does(tmp_path: Path):
    """Found live on 2026-10-01: the reference configuration keeps its DEFAULT
    state backend in cfg/state-backends-2.yml beside a non-default one in
    cfg/state-backends.yml; reading the canonical file alone named the wrong
    bucket, absent, and the root would have created it."""
    root = _starter_copy(tmp_path)
    _filled(root)
    first = root / "cfg" / "state-backends.yml"
    first.write_text(first.read_text().replace("is_default: true", "is_default: false").replace("acme-tfstate", "an-old-sample-bucket"))
    (root / "cfg" / "state-backends-2.yml").write_text(
        "state_backends:\n  - name: s3-real\n    type: s3\n    is_default: true\n    bucket: acme-real-tfstate\n"
        "    key: statefiles/real/\n    region: us-west-2\n")
    facts = _facts(root, _account(oidc=True, read=True, write=True, bucket=True, profile=True))
    assert [b["name"] for b in facts.state_backends] == ["s3-real", "s3-main"]      # both files, in name order
    default = default_state_backend(facts, "s3")
    assert default is not None and default["bucket"] == "acme-real-tfstate"         # the default, wherever it is declared
    a = bs.run_interview([_section()], facts, quiet=True)["aws"]
    assert (a["state_bucket"], a["state_prefix"], a["state_region"]) == ("acme-real-tfstate", "statefiles/real", "us-west-2")


# ----------------------------------------------------------------- the root it makes

def _root(tmp_path: Path, **present: bool) -> tuple[Path, Path]:
    root = _starter_copy(tmp_path)
    _filled(root)
    facts = _facts(root, _account(**present))
    answers = bs.run_interview(bs.discover(), facts, quiet=True)
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    assert bs.regenerate(root)
    return root, bs.output_dir(root)


def test_what_exists_is_read_or_adopted_and_the_state_binds_to_the_bucket_that_stands(tmp_path: Path):
    root, out = _root(tmp_path, oidc=True, read=True, write=False, bucket=True, profile=True)
    main = (out / "main.tf").read_text()
    assert 'module "bootstrap_aws"' in main and 'module "bootstrap_github"' in main
    assert _assigned(main, "source", '"../../tfmodules/bootstrap_aws"')
    imports = re.findall(r"import \{\n  to = (\S+)\n  id = \"([^\"]+)\"\n\}", main)
    assert imports == [("module.bootstrap_aws.aws_iam_role.read", "csis-github-readonly")]   # the one that stands, adopted
    providers = (out / "providers.tf").read_text()
    assert 'backend "s3" {' in providers and 'backend "local"' not in providers                # decision D8
    assert _assigned(providers, "bucket", '"acme-tfstate"') and _assigned(providers, "key", '"statefiles/my-team-images/bootstrap.tfstate"')
    assert _assigned(providers, "use_lockfile", "true") and _assigned(providers, "profile", '"acme"')
    assert 'source  = "hashicorp/aws"' in providers and 'source  = "integrations/github"' in providers
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    for key, value in (("aws_account_id", f'"{ACCOUNT}"'), ("aws_oidc_provider_exists", "true"),
                       ("aws_state_bucket_exists", "true"), ("aws_instance_profile_exists", "true"),
                       ("aws_subject_forms", '"both"'), ("aws_repo_id", '"987654"')):
        assert _assigned(tfvars, key, value), key
    assert '"ManagedBy"' in tfvars and "cs-image-system-bootstrap" in tfvars
    # the two role ARNs come from the applied root now, not from files; the rest still from files
    script = (out / "set-secrets.sh").read_text()
    assert "from_output AWS_ROLE_ARN aws_read_role_arn" in script and "from_output AWS_APPLY_ROLE_ARN aws_write_role_arn" in script
    assert "from_file AWS_ROLE_ARN" not in script and "from_file TF_VAR_KEY" in script
    readme = (out / "README.md").read_text()
    assert "adopted by import: csis-github-readonly" in readme and "is in the tree's declared backend" in readme


def test_a_bucket_the_bootstrap_makes_means_local_state_first(tmp_path: Path):
    root, out = _root(tmp_path, oidc=False, read=False, write=False, bucket=False, profile=False)
    providers = (out / "providers.tf").read_text()
    assert 'backend "local" {}' in providers and 'backend "s3"' not in providers
    assert "import {" not in (out / "main.tf").read_text()                     # nothing stands: nothing to adopt
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "aws_state_bucket_exists", "false") and _assigned(tfvars, "aws_oidc_provider_exists", "false")
    readme = (out / "README.md").read_text()
    assert "is CREATED here (versioned, encrypted, private): local state for this first apply" in readme
    assert "re-run the\ninterview" in readme and "-migrate-state" in readme     # how the state gets to the bucket afterwards
    # a second interview with the bucket now standing binds the root to it, and keeps every other answer
    facts = _facts(root, _account(oidc=True, read=True, write=True, bucket=True, profile=True))
    prior = bs.read_answers(root / bs.ANSWERS_FILE)
    prior["aws"].pop("state_bucket_exists")                                     # the operator re-asks that one question
    bs.write_answers(root / bs.ANSWERS_FILE, bs.run_interview(bs.discover(), facts, quiet=True, prior=prior))
    bs.regenerate(root)
    assert 'backend "s3" {' in (out / "providers.tf").read_text()
    assert bs.read_answers(root / bs.ANSWERS_FILE)["aws"]["read_role_exists"] is False   # an earlier answer is kept, not re-probed


def test_the_module_says_what_the_guide_says():
    """The module's documents are the guide's (CI_SETUP.md 3.3): the same
    statements by Sid, the write role trusted on the production branch alone."""
    module = (REPO / "tfmodules" / "bootstrap_aws" / "main.tf").read_text()
    guide = (EXAMPLES / "complete" / "CI_SETUP.md").read_text()
    section = guide[guide.index("### 3.3 AWS"):guide.index("### 3.4 GCP")]
    sids = set(re.findall(r'"Sid": "(\w+)"', section))
    assert sids and sids == set(re.findall(r'Sid\s*=\s*"(\w+)"', module)), sids
    for action in ("ec2:RunInstances", "ssm:StartSession", "iam:PassRole", "s3:GetBucketTagging", "iam:GetInstanceProfile"):
        assert action in section and action in module, action
    assert ':ref:refs/heads/${var.production_branch}' in module and '"${f}:*"' in module
    assert "aws_iam_openid_connect_provider" in module and "AmazonSSMManagedInstanceCore" in module
    for name in TREES:
        assert (EXAMPLES / name / "tfmodules" / "bootstrap_aws" / "main.tf").read_bytes() == (REPO / "tfmodules" / "bootstrap_aws" / "main.tf").read_bytes()


@pytest.mark.skipif(shutil.which("tofu") is None, reason="tofu not installed")
def test_the_root_with_both_sections_validates_with_tofu(tmp_path: Path):
    from tests.test_v2_gcp_increment3 import private_plugin_cache
    root, out = _root(tmp_path, oidc=True, read=True, write=True, bucket=True, profile=False)
    env = {**os.environ, "TF_PLUGIN_CACHE_DIR": str(private_plugin_cache(tmp_path, [out, REPO / "tfmodules" / "bootstrap_aws"]))}
    for args in (["init", "-backend=false", "-input=false", "-no-color"], ["validate", "-no-color"]):
        res = subprocess.run(["tofu", *args], cwd=out, capture_output=True, text=True, timeout=600, env=env)
        assert res.returncode == 0, f"tofu {args[0]}\n{res.stdout}\n{res.stderr}"
