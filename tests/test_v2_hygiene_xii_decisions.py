# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XII, group G: the operator's decisions of 2026-10-14.

- Item 5: a state bucket the bootstrap made stays managed by the root; the
  second interview observes that it stands and binds the backend, and no
  bucket resource leaves the plan.
- Item 15: usernames are public; the starters write them in clear.
- Item 21: a bake stamps and fingerprints only the storage types whose
  builder lives on its runtime.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tests.test_v2_bootstrap import EXAMPLES, REPO, _assigned, _starter_copy
from tests.test_v2_bootstrap_aws import _account, _facts, _filled
from v2_support import V2Run

from cs_image_system.base import bootstrap as bs

TREES_WITH_OPA = ("complete", "standard-aws", "standard-gce")


# ------------------------------------------------------------ item 5

def test_a_bucket_the_root_made_stays_managed_after_the_second_interview(tmp_path: Path):
    root = _starter_copy(tmp_path)
    _filled(root)
    first = _facts(root, _account(oidc=False, read=False, write=False, bucket=False, profile=False))
    answers = bs.run_interview(bs.discover(), first, quiet=True, only=["github", "aws"])
    assert answers["aws"]["state_bucket_exists"] is False and answers["aws"]["state_bucket_managed"] is True
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    assert bs.regenerate(root)
    out = bs.output_dir(root)
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "aws_state_bucket_exists", "false") and _assigned(tfvars, "aws_state_bucket_managed", "true")
    assert "is CREATED here (versioned, encrypted, private) and managed from then on" in (out / "README.md").read_text()
    # the second interview, the bucket now standing: observed (no answer to pop), the backend binds,
    # and the bucket stays managed -- the four resources do not leave the plan
    second = _facts(root, _account(oidc=True, read=True, write=True, bucket=True, profile=True))
    prior = bs.read_answers(root / bs.ANSWERS_FILE)
    again = bs.run_interview(bs.discover(), second, quiet=True, prior=prior, only=["github", "aws"])
    assert again["aws"]["state_bucket_exists"] is True and again["aws"]["state_bucket_managed"] is True
    bs.write_answers(root / bs.ANSWERS_FILE, again)
    assert bs.regenerate(root)
    assert 'backend "s3" {' in (out / "providers.tf").read_text()
    tfvars = (out / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "aws_state_bucket_exists", "true") and _assigned(tfvars, "aws_state_bucket_managed", "true")
    readme = (out / "README.md").read_text()
    assert "exists and is MANAGED here (made by an earlier apply of this root; a destroy of the root removes it)" in readme
    # a bucket that stood before the root is read and never managed
    theirs = _starter_copy(tmp_path / "theirs")
    _filled(theirs)
    a = bs.run_interview(bs.discover(), _facts(theirs, _account(oidc=True, read=True, write=True, bucket=True, profile=True)),
                         quiet=True, only=["github", "aws"])["aws"]
    assert a["state_bucket_exists"] is True and a["state_bucket_managed"] is False
    bs.write_answers(theirs / bs.ANSWERS_FILE, {"aws": a, "github": {"wanted": False}})
    assert bs.regenerate(theirs)
    tfvars = (bs.output_dir(theirs) / "bootstrap.auto.tfvars").read_text()
    assert _assigned(tfvars, "aws_state_bucket_managed", "false")
    assert "stood before this root and is not managed here" in (bs.output_dir(theirs) / "README.md").read_text()
    # the module counts the bucket resources on `managed`, never on `exists`, in every copy
    for path in [REPO / "tfmodules" / "bootstrap_aws" / "main.tf"] + [
            EXAMPLES / n / "tfmodules" / "bootstrap_aws" / "main.tf" for n in ("complete", "standard-aws", "standard-aws-posix", "standard-gce")]:
        module = path.read_text()
        assert module.count("var.state_bucket_managed ? 1 : 0") == 4 and "state_bucket_exists ? 0 : 1" not in module, path


# ------------------------------------------------------------ item 15

def test_the_starters_write_usernames_in_clear_and_say_why():
    for name in TREES_WITH_OPA:
        path = EXAMPLES / name / "groups" / "users.yaml"
        users = yaml.safe_load(path.read_text())["users"]
        assert users and all(not str(u["name"]).startswith("ENC[") for u in users), name
        assert "committed in clear" in path.read_text() or "committed IN CLEAR" in path.read_text(), name
    guide = (REPO / "docs" / "CONFIGURATION.md").read_text()
    assert "**What a marker protects**" in guide and "Usernames are therefore public by decision" in guide
    assert "| `name` | str | required | the username" in guide
    driver = (REPO / "DAILY_DRIVER.md").read_text()
    assert "username is committed in clear" in driver


# ------------------------------------------------------------ item 21

def test_a_bake_stamps_and_fingerprints_the_storage_types_of_its_runtime_alone(tmp_path, monkeypatch):
    from cs_image_system.base.capabilities import declared_capabilities, effective_capabilities
    from cs_image_system.base.lineage import BaseImageRef, capability_stamp, input_fingerprint
    run = V2Run(tmp_path, monkeypatch)
    try:
        ctx = run.ctx
        osb = ctx.os_builders["basic-rh-10"]
        assert osb.model.get_storage_types() == ["ebs", "efs", "s3", "pd", "gcs"]
        base = BaseImageRef("basic-rh-10", osb.model)             # the plan-time stand-in a base image fingerprints as
        assert declared_capabilities(ctx, "basic-rh-10")["storage_types"] == ["ebs", "efs", "gcs", "pd", "s3"]
        assert declared_capabilities(ctx, "basic-rh-10", "aws-east2-runtime")["storage_types"] == ["ebs", "efs", "s3"]
        assert declared_capabilities(ctx, "basic-rh-10", "gcloud-east1")["storage_types"] == ["gcs", "pd"]
        assert capability_stamp(ctx, base, "aws-east2-runtime")["storage_types"] == ["ebs", "efs", "s3"]
        assert capability_stamp(ctx, base, "gcloud-east1")["storage_types"] == ["gcs", "pd"]
        # the declaration path of an instance image's effective capabilities is per runtime too
        img = ctx.images_map["imgfile-basic-dask"]
        caps = effective_capabilities(ctx, img, "gcloud-east1")
        assert caps is not None and caps.source == "declaration" and caps.storage_types == ["gcs", "pd"]
        whole = effective_capabilities(ctx, img)                                          # no runtime: as declared
        assert whole is not None and whole.storage_types == ["ebs", "efs", "gcs", "pd", "s3"]
        # the walk's F49: a type for the other cloud added or removed moves no AWS fingerprint
        before = input_fingerprint(ctx, base, "aws-east2-runtime")
        before_gce = input_fingerprint(ctx, base, "gcloud-east1")
        osb.model.storage_types = ["ebs", "efs", "s3", "gcs"]                  # pd dropped
        base = BaseImageRef("basic-rh-10", osb.model)
        assert input_fingerprint(ctx, base, "aws-east2-runtime") == before
        assert input_fingerprint(ctx, base, "gcloud-east1") != before_gce
        osb.model.storage_types = ["ebs", "s3", "pd", "gcs"]                   # efs dropped instead
        base = BaseImageRef("basic-rh-10", osb.model)
        assert input_fingerprint(ctx, base, "aws-east2-runtime") != before
    finally:
        run.restore_cwd()
