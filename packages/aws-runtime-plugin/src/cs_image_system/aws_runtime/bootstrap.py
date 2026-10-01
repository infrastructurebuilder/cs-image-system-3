# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The AWS section of the bootstrap (stage 70 step 4; CI_SETUP.md 3.3).

What terraform makes, per the guide: the GitHub OIDC identity provider, the
READ-ONLY role and the WRITE role with their trust documents (the subject
forms the interview chose: plain, id-bearing, or both) and permission
policies (the guide's, with the interview's bucket, prefix, region, account
and instance profile filled in), and optionally the state bucket (versioned,
encrypted, private) and the SSM instance profile when the account lacks
them. The network is never touched.

Every "existing" question is a fork, and its default is a PROBE of the
account when a session is there (``aws iam get-role``, ``head-bucket``...):
exists means a data source or an ``import`` block that adopts it, absent
means the resource. With no session a probe cannot answer, so ``--quiet``
refuses that question by name rather than guess -- a wrong guess is a failed
apply at best. A starter's placeholders (``REPLACE-ME``, the example
account id) are no defaults either.

The root's state binds to the tree's declared S3 backend when the bucket
exists (decision D8); when the bootstrap creates the bucket, the first apply
is local and a second interview, the bucket now standing, binds it.
"""

from __future__ import annotations

from typing import Any

from cs_image_system.base.bootstrap.facts import Facts, default_state_backend, real, runtime_of_type
from cs_image_system.base.bootstrap.questions import Answers, Question, Raw, Rendered, Secret, Section

MODULE = "bootstrap_aws"
OIDC_HOST = "token.actions.githubusercontent.com"
MANAGED_BY = "cs-image-system-bootstrap"


# ------------------------------------------------------------------ the account
def _runtime(facts: Facts) -> dict[str, Any]:
    return runtime_of_type(facts, "aws") or {}


def _profile_of(facts: Facts, answers: Answers) -> str:
    if "profile" in answers:
        return str(answers.get("profile") or "")
    return real((_runtime(facts).get("credentials") or {}).get("profile_name")) or ""


def _aws(facts: Facts, answers: Answers, *args: str) -> tuple[int, str]:
    cmd = ["aws", *args]
    profile = _profile_of(facts, answers)
    if profile:
        cmd += ["--profile", profile]
    return facts.probe(cmd)


def _exists(result: tuple[int, str], absent_marks: tuple[str, ...]) -> bool | None:
    """True when the probe found it, False when the account SAID it is not
    there, None when the probe could not ask (no tool, no session, denied)."""
    code, out = result
    if code == 0:
        return True
    if any(mark in out for mark in absent_marks):
        return False
    return None


def _oidc_exists(facts: Facts, answers: Answers) -> bool | None:
    account = answers.get("account_id")
    if not account:
        return None
    arn = f"arn:aws:iam::{account}:oidc-provider/{OIDC_HOST}"
    return _exists(_aws(facts, answers, "iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", arn),
                   ("NoSuchEntity",))


def _role_exists(key: str):
    def probe(facts: Facts, answers: Answers) -> bool | None:
        name = answers.get(key)
        return _exists(_aws(facts, answers, "iam", "get-role", "--role-name", str(name)), ("NoSuchEntity",)) if name else None
    return probe


def _bucket_exists(facts: Facts, answers: Answers) -> bool | None:
    bucket = answers.get("state_bucket")
    if not bucket:
        return None
    return _exists(_aws(facts, answers, "s3api", "head-bucket", "--bucket", str(bucket)),
                   ("Not Found", "404", "NoSuchBucket"))


def _profile_exists(facts: Facts, answers: Answers) -> bool | None:
    name = answers.get("instance_profile")
    if not name:
        return None
    return _exists(_aws(facts, answers, "iam", "get-instance-profile", "--instance-profile-name", str(name)),
                   ("NoSuchEntity",))


# -------------------------------------------------------------------- defaults
def _state(facts: Facts, key: str) -> str | None:
    return real((default_state_backend(facts, "s3") or {}).get(key))


def _state_prefix(facts: Facts, answers: Answers) -> str | None:
    prefix = _state(facts, "key")
    return prefix.strip("/") if prefix else None


def _forms_default(facts: Facts, answers: Answers) -> str:
    return "both" if facts.owner_id and facts.repo_id else "plain"


def _needs_ids(answers: Answers) -> bool:
    return answers.get("subject_forms") in ("ids", "both")


def _tags_default(facts: Facts, answers: Answers) -> str:
    tags = _runtime(facts).get("tags") or {}
    pairs = [f"{k}={v}" for k, v in sorted(tags.items()) if real(v)] if isinstance(tags, dict) else []
    return ",".join(pairs)


def _session_profile(facts: Facts, answers: Answers) -> str | None:
    rt = _runtime(facts)
    return real(rt.get("session_instance_profile")) or real(rt.get("iam_instance_profile"))


def parse_tags(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(text or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


QUESTIONS: tuple[Question, ...] = (
    Question("account_id", "The AWS account id", default=lambda f, a: real(_runtime(f).get("account_id")),
             help="the AWS runtime's `account_id` in cfg/runtime-builders.yml is unset or still the starter's example"),
    Question("region", "The region of the AWS runtime", default=lambda f, a: real(_runtime(f).get("region")),
             help="the AWS runtime's `region` in cfg/runtime-builders.yml"),
    Question("profile", "The AWS profile you apply this root with (empty to use the environment's credentials)",
             default=lambda f, a: _profile_of(f, {})),
    Question("repository", "The GitHub repository the roles trust, as owner/name", default=lambda f, a: f.repository,
             help="read from `git remote get-url origin` when the checkout has a GitHub remote"),
    Question("production_branch", "The branch the WRITE role trusts (the perform job's)", default="main"),
    Question("subject_forms", "Which OIDC subject forms the roles trust: the plain name form, the id-bearing form "
             "(an organisation that customises the subject), or both", kind="choice",
             choices=("plain", "ids", "both"), default=_forms_default),
    Question("owner_id", "The repository owner's numeric id (`gh api users/<owner> --jq .id`)", when=_needs_ids,
             default=lambda f, a: str(f.owner_id) if f.owner_id else None, help="`gh` is absent or not logged in"),
    Question("repo_id", "The repository's numeric id (`gh api repos/<owner>/<repo> --jq .id`)", when=_needs_ids,
             default=lambda f, a: str(f.repo_id) if f.repo_id else None, help="`gh` is absent or not logged in"),
    Question("oidc_provider_exists", "Does the account already have the GitHub OIDC identity provider "
             f"({OIDC_HOST})?", kind="bool", default=_oidc_exists,
             help="the account could not be asked: no AWS session, or `aws` is not installed"),
    Question("read_role_name", "The READ-ONLY role's name (AWS_ROLE_ARN)", default="csis-github-readonly"),
    Question("read_role_exists", "Does the READ-ONLY role already exist (it is then adopted by import)?", kind="bool",
             default=_role_exists("read_role_name"), help="the account could not be asked: no AWS session"),
    Question("write_role_name", "The WRITE role's name (AWS_APPLY_ROLE_ARN)", default="csis-github-apply"),
    Question("write_role_exists", "Does the WRITE role already exist (it is then adopted by import)?", kind="bool",
             default=_role_exists("write_role_name"), help="the account could not be asked: no AWS session"),
    Question("state_bucket", "The state bucket's name", default=lambda f, a: _state(f, "bucket"),
             help="the default S3 backend's `bucket` in cfg/state-backends.yml is unset or still the starter's placeholder"),
    Question("state_prefix", "The state key prefix within the bucket", default=_state_prefix,
             help="the default S3 backend's `key` in cfg/state-backends.yml"),
    Question("state_region", "The state bucket's region",
             default=lambda f, a: _state(f, "region") or a.get("region")),
    Question("state_bucket_exists", "Does the state bucket already exist?", kind="bool", default=_bucket_exists,
             help="the account could not be asked: no AWS session"),
    Question("instance_profile", "The instance profile build and standing instances wear for Session Manager",
             default=_session_profile,
             help="the AWS runtime's `session_instance_profile` in cfg/runtime-builders.yml is unset or a placeholder"),
    Question("instance_profile_exists", "Does that instance profile already exist?", kind="bool",
             default=_profile_exists, help="the account could not be asked: no AWS session"),
    Question("tags", "Tags for everything this root makes, as k=v,k=v (empty for none)", default=_tags_default),
)


def render(answers: Answers) -> Rendered:
    profile = str(answers.get("profile") or "")
    prefix = str(answers["state_prefix"]).strip("/")
    tags = {**parse_tags(str(answers.get("tags") or "")), "ManagedBy": MANAGED_BY}
    bucket_exists = bool(answers["state_bucket_exists"])
    backend = None
    if bucket_exists:
        settings: dict[str, Any] = {"bucket": answers["state_bucket"], "key": f"{prefix}/bootstrap.tfstate",
                                    "region": answers["state_region"], "encrypt": True, "use_lockfile": True}
        if profile:
            settings["profile"] = profile
        backend = ("s3", settings)
    imports = ""
    for key, address in (("read", "read"), ("write", "write")):
        if answers.get(f"{key}_role_exists"):
            imports += (f"# the {key.upper()} role already stands: adopted, so its trust and policy are maintained from here\n"
                        f"import {{\n  to = module.{MODULE}.aws_iam_role.{address}\n  id = \"{answers[f'{key}_role_name']}\"\n}}\n\n")
    names = ("account_id", "region", "repository", "production_branch", "subject_forms", "owner_id", "repo_id",
             "oidc_provider_exists", "read_role_name", "write_role_name", "state_bucket", "state_prefix",
             "state_bucket_exists", "instance_profile", "instance_profile_exists")
    types = {"oidc_provider_exists": "bool", "state_bucket_exists": "bool", "instance_profile_exists": "bool"}
    described = {
        "account_id": "the AWS account", "region": "the AWS runtime's region",
        "repository": "the GitHub repository the roles trust, as owner/name",
        "production_branch": "the branch the WRITE role trusts",
        "subject_forms": "the OIDC subject forms trusted: plain, ids or both",
        "owner_id": "the repository owner's numeric id (empty when the plain form alone is trusted)",
        "repo_id": "the repository's numeric id (empty when the plain form alone is trusted)",
        "oidc_provider_exists": "the account already has the GitHub OIDC provider (read, not made)",
        "read_role_name": "the READ-ONLY role's name", "write_role_name": "the WRITE role's name",
        "state_bucket": "the state bucket", "state_prefix": "the state key prefix",
        "state_bucket_exists": "the state bucket already exists (not made)",
        "instance_profile": "the Session Manager instance profile",
        "instance_profile_exists": "the instance profile already exists (read, not made)",
    }
    variables = tuple((f"aws_{n}", types.get(n, "string"), described[n]) for n in names) + (
        ("aws_profile", "string", "the AWS profile this root is applied with (empty: the environment's credentials)"),
        ("aws_tags", "map(string)", "tags on everything this root makes"),
    )
    tfvars: dict[str, Any] = {f"aws_{n}": (bool(answers[n]) if n in types else str(answers.get(n) or "")) for n in names}
    tfvars["aws_state_prefix"] = prefix
    tfvars["aws_profile"] = profile
    tfvars["aws_tags"] = tags
    adopted = [answers[f"{k}_role_name"] for k in ("read", "write") if answers.get(f"{k}_role_exists")]
    return Rendered(
        module=MODULE,
        module_args={n: Raw(f"var.aws_{n}") for n in names},
        variables=variables,
        tfvars=tfvars,
        outputs=(
            ("aws_read_role_arn", f"module.{MODULE}.read_role_arn", "the READ-ONLY role's ARN: the AWS_ROLE_ARN secret"),
            ("aws_write_role_arn", f"module.{MODULE}.write_role_arn", "the WRITE role's ARN: the AWS_APPLY_ROLE_ARN secret"),
            ("aws_oidc_provider_arn", f"module.{MODULE}.oidc_provider_arn", "the GitHub OIDC identity provider"),
            ("aws_state_bucket", f"module.{MODULE}.state_bucket", "the state bucket"),
            ("aws_instance_profile_arn", f"module.{MODULE}.instance_profile_arn", "the Session Manager instance profile"),
        ),
        required_providers={"aws": {"source": "hashicorp/aws", "version": ">= 5.81"}},
        provider_blocks=('provider "aws" {\n  region  = var.aws_region\n'
                         '  profile = var.aws_profile != "" ? var.aws_profile : null\n'
                         '  default_tags {\n    tags = var.aws_tags\n  }\n}\n'),
        secrets=(
            Secret("AWS_ROLE_ARN", "output", "aws_read_role_arn", "the READ-ONLY role's ARN, from the applied root"),
            Secret("AWS_APPLY_ROLE_ARN", "output", "aws_write_role_arn", "the WRITE role's ARN, from the applied root"),
        ),
        by_hand=(
            "The network (VPC, subnets, security groups, the access gateway): the team's, never modified by the system.",
            "If an adopted role carries an inline policy made by hand, it stays beside the managed one: once the plan "
            "is clean and CI is green, remove the hand-made policy in the console so one document is the truth.",
            "The first performing run (CI_SETUP.md 3.8), after the secrets are set.",
        ),
        notes=(
            f"account `{answers['account_id']}`, region `{answers['region']}`; the GitHub OIDC provider "
            + ("read (it exists)" if answers["oidc_provider_exists"] else "created"),
            f"the READ-ONLY role `{answers['read_role_name']}` (any ref of `{answers['repository']}`) and the WRITE role "
            f"`{answers['write_role_name']}` (`{answers['production_branch']}` alone), subject forms: {answers['subject_forms']}"
            + (f"; adopted by import: {', '.join(adopted)}" if adopted else ""),
            f"the state bucket `{answers['state_bucket']}` " + ("exists: this root's state is bound to it (decision D8)"
                                                                 if bucket_exists else
                                                                 "is CREATED here (versioned, encrypted, private): local state for this first apply"),
            f"the instance profile `{answers['instance_profile']}` "
            + ("read (it exists)" if answers["instance_profile_exists"] else "created with AmazonSSMManagedInstanceCore"),
        ),
        backend=backend,
        root_hcl=imports,
    )


def wanted(facts: Facts) -> bool:
    """The tree uses AWS: it declares an AWS runtime or keeps its state in S3."""
    return runtime_of_type(facts, "aws") is not None or default_state_backend(facts, "s3") is not None


def aws_section() -> Section:
    return Section(name="aws", title="AWS", questions=QUESTIONS, render=render, wanted=wanted,
                   description="the GitHub OIDC provider, the read-only and write roles, the optional state bucket and instance profile")
