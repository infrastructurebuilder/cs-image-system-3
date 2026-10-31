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

import json
from typing import Any

from cs_image_system.base.bootstrap.facts import (Facts, bound_backend_names, default_state_backend, other_state_backends,
                                                   real, runtime_of_type)
from cs_image_system.base.bootstrap.questions import (ADOPTED, BY_HAND, MADE, READ, Answers, Question, Raw, Rendered,
                                                       Secret, Section)

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


def trusted_subjects(document: Any) -> list[str]:
    """Every OIDC subject a trust document admits, in order, whatever the
    operator (StringLike, StringEquals) and whether one value or a list."""
    out: list[str] = []
    statements = (document or {}).get("Statement") or []
    for st in statements if isinstance(statements, list) else [statements]:
        for values in ((st or {}).get("Condition") or {}).values():
            for key, subs in (values or {}).items():
                if str(key).endswith(":sub"):
                    for s in subs if isinstance(subs, list) else [subs]:
                        if s not in out:
                            out.append(str(s))
    return out


def _extra_subjects(kind: str):
    """The subjects an EXISTING role trusts that are not this repository's:
    another repository's CI may share the role (the reference account's
    read-only role serves the system's own repository too, and the first
    live plan of an adoption would have removed it). Adopting a role keeps
    them by default; the prompt shows them so a person can drop them. A role
    that does not exist has none; one whose trust cannot be read has no
    default."""
    def default(facts: Facts, answers: Answers) -> str | None:
        if not answers.get(f"{kind}_role_exists"):
            return ""
        code, out = _aws(facts, answers, "iam", "get-role", "--role-name", str(answers[f"{kind}_role_name"]),
                         "--query", "Role.AssumeRolePolicyDocument", "--output", "json")
        if code != 0:
            return None
        try:
            document = json.loads(out[out.index("{"):out.rindex("}") + 1]) if "{" in out else {}
        except ValueError:
            return None
        repository = str(answers.get("repository") or "")
        owner, _, name = repository.partition("/")
        mine = (f"repo:{repository}:", f"repo:{owner}@{answers.get('owner_id')}/{name}@{answers.get('repo_id')}:")
        return ",".join(s for s in trusted_subjects(document) if not s.startswith(mine))
    return default


def parse_subjects(text: Any) -> list[str]:
    return [s.strip() for s in str(text or "").split(",") if s.strip()]


def _bucket_exists(facts: Facts, answers: Answers) -> bool | None:
    bucket = answers.get("state_bucket")
    if not bucket:
        return None
    return _exists(_aws(facts, answers, "s3api", "head-bucket", "--bucket", str(bucket)),
                   ("Not Found", "404", "NoSuchBucket"))


def _bucket_named_exists(facts: Facts, answers: Answers, bucket: str) -> bool | None:
    return _exists(_aws(facts, answers, "s3api", "head-bucket", "--bucket", bucket), ("Not Found", "404", "NoSuchBucket"))


def other_s3_buckets(facts: Facts) -> list[tuple[str, str, str, bool]]:
    """The tree's other S3 backends (hygiene XX item 1): ``(backend name,
    bucket, prefix, bound)`` for each with a real bucket, in declaration
    order; ``bound`` when some root's ``state_configuration`` names it."""
    bound = bound_backend_names(facts)
    out: list[tuple[str, str, str, bool]] = []
    for backend in other_state_backends(facts, "s3"):
        bucket = real(backend.get("bucket"))
        if not bucket:
            continue
        prefix = (real(backend.get("key")) or "").strip("/")
        out.append((str(backend["name"]), bucket, prefix, str(backend["name"]) in bound))
    return out


def _other_buckets_default(facts: Facts, answers: Answers) -> str | None:
    """The other S3 backends' buckets this root should make: every one that
    is bound to a root and that the account says is absent, as
    ``bucket=prefix,...``; a bucket bound to no root is left out (the README
    says so); a bucket the account cannot be asked about leaves no default."""
    pairs: list[str] = []
    for _name, bucket, prefix, bound in other_s3_buckets(facts):
        if not bound:
            continue
        exists = _bucket_named_exists(facts, answers, bucket)
        if exists is None:
            return None
        if not exists:
            pairs.append(f"{bucket}={prefix}")
    return ",".join(pairs)


def parse_buckets(text: Any) -> dict[str, str]:
    """``bucket=prefix,bucket=prefix`` as a mapping (an empty prefix allowed)."""
    out: dict[str, str] = {}
    for part in str(text or "").split(","):
        part = part.strip()
        if not part:
            continue
        bucket, _, prefix = part.partition("=")
        if bucket.strip():
            out[bucket.strip()] = prefix.strip().strip("/")
    return out


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
    Question("profile", "The AWS profile you apply this root with (none to use the environment's credentials)",
             default=lambda f, a: _profile_of(f, {}), may_be_empty=True),
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
    Question("read_extra_subjects", "Other OIDC subjects the READ-ONLY role keeps trusting, comma-separated (an "
             "existing role's subjects that are not this repository's)",
             default=_extra_subjects("read"), help="the existing role's trust could not be read: no AWS session",
             may_be_empty=True),
    Question("write_role_name", "The WRITE role's name (AWS_APPLY_ROLE_ARN)", default="csis-github-apply"),
    Question("write_role_exists", "Does the WRITE role already exist (it is then adopted by import)?", kind="bool",
             default=_role_exists("write_role_name"), help="the account could not be asked: no AWS session"),
    Question("write_extra_subjects", "Other OIDC subjects the WRITE role keeps trusting, comma-separated",
             default=_extra_subjects("write"), help="the existing role's trust could not be read: no AWS session",
             may_be_empty=True),
    Question("state_bucket", "The state bucket's name", default=lambda f, a: _state(f, "bucket"),
             help="the default S3 backend's `bucket` in cfg/state-backends.yml is unset or still the starter's placeholder"),
    Question("state_prefix", "The state key prefix within the bucket", default=_state_prefix,
             help="the default S3 backend's `key` in cfg/state-backends.yml"),
    Question("state_region", "The state bucket's region",
             default=lambda f, a: _state(f, "region") or a.get("region")),
    Question("state_bucket_exists", "Does the state bucket already exist?", kind="bool", default=_bucket_exists,
             help="the account could not be asked: no AWS session", observed=True),
    # hygiene XII item 5 (the walk's F17): the second interview, run so the
    # root binds to the bucket it made, answered "exists" and the module's
    # four bucket resources went to count 0 while they sat in the state --
    # the next plan destroyed versioning, encryption and the access block.
    # Whether the bucket STANDS is observed each time (above); whether this
    # root MANAGES it is a choice recorded once, and a bucket the root makes
    # is managed from then on.
    Question("state_bucket_managed", "Does this root MANAGE the state bucket: made by an apply of this root and kept "
             "here, so a destroy of the root removes it? (a bucket that stood before this root is read, never "
             "managed; one this root makes is managed from then on)", kind="bool",
             default=lambda f, a: not a.get("state_bucket_exists")),
    # hygiene XX item 1: the tree's OTHER S3 backends. A choice, not an
    # observation: the second interview keeps the answer, so a bucket this
    # root made never leaves the plan (the trap item 5 of hygiene XII closed
    # for the default bucket).
    Question("other_state_buckets", "The tree's other S3 backends' buckets this root MAKES when absent and manages "
             "from then on, as bucket=prefix,bucket=prefix (by default every one bound to a root that the account "
             "says is absent; a backend bound to no root is left out)", default=_other_buckets_default,
             help="the account could not be asked about one of the other buckets: no AWS session", may_be_empty=True),
    Question("instance_profile", "The instance profile build and standing instances wear for Session Manager",
             default=_session_profile,
             help="the AWS runtime's `session_instance_profile` in cfg/runtime-builders.yml is unset or a placeholder"),
    Question("instance_profile_exists", "Does that instance profile already exist?", kind="bool",
             default=_profile_exists, help="the account could not be asked: no AWS session"),
    Question("tags", "Tags for everything this root makes, as k=v,k=v", default=_tags_default, may_be_empty=True),
)


def render(answers: Answers, facts: Facts | None = None) -> Rendered:
    profile = str(answers.get("profile") or "")
    prefix = str(answers["state_prefix"]).strip("/")
    tags = {**parse_tags(str(answers.get("tags") or "")), "ManagedBy": MANAGED_BY}
    bucket_exists = bool(answers["state_bucket_exists"])
    bucket_managed = bool(answers.get("state_bucket_managed")) or not bucket_exists   # made here: managed, always
    other_made = parse_buckets(answers.get("other_state_buckets"))
    # the other backends this root does NOT make, with the reason (item 1: a line, never a silence)
    others = other_s3_buckets(facts) if facts is not None else []
    other_rows: list[tuple[str, str, str]] = []
    for name, bucket, _bprefix, bound in others:
        if bucket in other_made:
            other_rows.append((f"the S3 backend `{name}`'s bucket `{bucket}`", MADE,
                               "declared, bound to a root and absent at the interview: made here (versioned, encrypted, private) and managed from then on"))
        elif not bound:
            other_rows.append((f"the S3 backend `{name}`'s bucket `{bucket}`", BY_HAND,
                               "declared but bound to no root, so nothing would use it: not made; bind a root to it and re-run the interview, or drop the backend"))
        else:
            other_rows.append((f"the S3 backend `{name}`'s bucket `{bucket}`", READ,
                               "stood at the interview, or was left out of the answer: read, never managed here"))
    for bucket in other_made:
        if bucket not in {b for _n, b, _p, _b in others}:
            other_rows.append((f"the bucket `{bucket}`", MADE, "named in the answer; no declared S3 backend names it"))
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
             "state_bucket_exists", "state_bucket_managed", "instance_profile", "instance_profile_exists")
    types = {"oidc_provider_exists": "bool", "state_bucket_exists": "bool", "state_bucket_managed": "bool",
             "instance_profile_exists": "bool"}
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
        "state_bucket_exists": "the state bucket already stands (observed at every interview; decides the backend)",
        "state_bucket_managed": "this root manages the state bucket: made by an apply of it and kept here "
                                "(decides the bucket resources; a destroy of the root removes the bucket)",
        "instance_profile": "the Session Manager instance profile",
        "instance_profile_exists": "the instance profile already exists (read, not made)",
    }
    variables = tuple((f"aws_{n}", types.get(n, "string"), described[n]) for n in names) + (
        ("aws_other_state_buckets", "map(string)", "the tree's other S3 backends' buckets this root makes and manages: bucket -> key prefix"),
        ("aws_profile", "string", "the AWS profile this root is applied with (empty: the environment's credentials)"),
        ("aws_tags", "map(string)", "tags on everything this root makes"),
        ("aws_read_extra_subjects", "list(string)", "other OIDC subjects the READ-ONLY role keeps trusting"),
        ("aws_write_extra_subjects", "list(string)", "other OIDC subjects the WRITE role keeps trusting"),
    )
    tfvars: dict[str, Any] = {f"aws_{n}": (bool(answers.get(n)) if n in types else str(answers.get(n) or ""))
                              for n in names}
    tfvars["aws_state_bucket_managed"] = bucket_managed
    tfvars["aws_state_prefix"] = prefix
    tfvars["aws_other_state_buckets"] = other_made
    tfvars["aws_profile"] = profile
    tfvars["aws_tags"] = tags
    extras = {k: parse_subjects(answers.get(f"{k}_extra_subjects")) for k in ("read", "write")}
    for k in ("read", "write"):
        tfvars[f"aws_{k}_extra_subjects"] = extras[k]
    adopted = [answers[f"{k}_role_name"] for k in ("read", "write") if answers.get(f"{k}_role_exists")]
    return Rendered(
        module=MODULE,
        destroy_takes=tuple(
            f"the {k.upper()} role `{answers[f'{k}_role_name']}`, adopted by import: the destroy deletes the role "
            "itself, with every subject it trusted" + (f" ({', '.join(f'`{s}`' for s in extras[k])} among them)"
                                                        if extras[k] else "")
            for k in ("read", "write") if answers.get(f"{k}_role_exists")),
        module_args={**{n: Raw(f"var.aws_{n}") for n in names},
                     "other_state_buckets": Raw("var.aws_other_state_buckets"),
                     "read_extra_subjects": Raw("var.aws_read_extra_subjects"),
                     "write_extra_subjects": Raw("var.aws_write_extra_subjects")},
        variables=variables,
        tfvars=tfvars,
        outputs=(
            ("aws_read_role_arn", f"module.{MODULE}.read_role_arn", "the READ-ONLY role's ARN: the AWS_ROLE_ARN secret"),
            ("aws_write_role_arn", f"module.{MODULE}.write_role_arn", "the WRITE role's ARN: the AWS_APPLY_ROLE_ARN secret"),
            ("aws_oidc_provider_arn", f"module.{MODULE}.oidc_provider_arn", "the GitHub OIDC identity provider"),
            ("aws_state_bucket", f"module.{MODULE}.state_bucket", "the state bucket"),
            ("aws_other_state_buckets", f"module.{MODULE}.other_state_buckets", "the other S3 backends' buckets made here"),
            ("aws_instance_profile_arn", f"module.{MODULE}.instance_profile_arn", "the Session Manager instance profile"),
        ),
        required_providers={"aws": {"source": "hashicorp/aws", "version": ">= 5.81"}},
        provider_blocks=('provider "aws" {\n  region  = var.aws_region\n'
                         '  profile = var.aws_profile != "" ? var.aws_profile : null\n'
                         '  default_tags {\n    tags = var.aws_tags\n  }\n}\n'),
        apply_env=(("AWS_PROFILE", profile, "the profile the interview probed the account as; its session must be "
                    "live (`aws sso login`), and it must be allowed to write IAM"),) if profile else (),
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
            *(f"the {k.upper()} role also keeps trusting: {', '.join(f'`{s}`' for s in extras[k])} (not this repository's; "
              "kept because the role already trusted them)" for k in ("read", "write") if extras[k]),
            f"the state bucket `{answers['state_bucket']}` "
            + ("exists and is MANAGED here (made by an earlier apply of this root; a destroy of the root removes it): "
               "this root's state is bound to it (decision D8)" if bucket_exists and bucket_managed else
               "exists: this root's state is bound to it (decision D8); the bucket stood before this root and is not managed here"
               if bucket_exists else
               "is CREATED here (versioned, encrypted, private) and managed from then on: local state for this first apply"),
            *(f"the S3 backend's bucket `{b}` (prefix `{p or '(none)'}`) is CREATED here (versioned, encrypted, private) "
              "and managed from then on" for b, p in sorted(other_made.items())),
            f"the instance profile `{answers['instance_profile']}` "
            + ("read (it exists)" if answers["instance_profile_exists"] else "created with AmazonSSMManagedInstanceCore"),
        ),
        backend=backend,
        root_hcl=imports,
        coverage=(
            ("the GitHub OIDC identity provider", READ if answers["oidc_provider_exists"] else MADE,
             "read as a data source when the account has it" if answers["oidc_provider_exists"] else "the account lacked it"),
            *((f"the {k.upper()} role `{answers[f'{k}_role_name']}`", ADOPTED if answers.get(f"{k}_role_exists") else MADE,
               "stood at the interview: an import block, so its trust and policy are maintained from here"
               if answers.get(f"{k}_role_exists") else "the account lacked it") for k in ("read", "write")),
            (f"the default S3 backend's bucket `{answers['state_bucket']}`",
             MADE if bucket_managed else READ,
             "made by an apply of this root and managed from then on" if bucket_managed
             else "stood before this root: read, never managed"),
            *other_rows,
            (f"the Session Manager instance profile `{answers['instance_profile']}`",
             READ if answers["instance_profile_exists"] else MADE,
             "read as a data source when the account has it" if answers["instance_profile_exists"]
             else "the account lacked it: a role with AmazonSSMManagedInstanceCore"),
            ("the network: VPC, subnets, security groups, the access gateway", BY_HAND,
             "the team's, by decision (stage 1's network rule): the system never creates or modifies network configuration"),
            ("the bake hosts' route to SSM and the package repositories", BY_HAND,
             "part of the network: the team's"),
        ),
    )


def wanted(facts: Facts) -> bool:
    """The tree uses AWS: it declares an AWS runtime or keeps its state in S3."""
    return runtime_of_type(facts, "aws") is not None or default_state_backend(facts, "s3") is not None


def aws_section() -> Section:
    return Section(name="aws", title="AWS", questions=QUESTIONS, render=render, wanted=wanted, wants_facts=True,
                   description="the GitHub OIDC provider, the read-only and write roles, the state buckets and the instance profile")
