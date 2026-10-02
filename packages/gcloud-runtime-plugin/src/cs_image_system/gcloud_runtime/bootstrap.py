# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The GCP section of the bootstrap (stage 70 step 5; CI_SETUP.md 3.4).

What terraform makes, per the guide: the workload identity pool and its
GitHub provider (the attribute mapping and the condition that admits this
repository), the READ-ONLY service account with the roles a load and the
state query read, the optional WRITE service account with the roles a bake
uses, and the ``workloadIdentityUser`` bindings that let the repository
impersonate them (the write one narrowed to the production branch).

What already exists is READ, never managed: an existing pool, provider or
service account becomes a data source. A provider's attribute condition may
admit other repositories that share it, so the bootstrap never rewrites one;
when an existing condition does not name this repository, the generated
README says so as a step by hand. Everything the module adds is additive --
project roles and bindings are single-member resources -- so no existing
grant is touched.

Every "existing" question's default is a PROBE through ``gcloud`` when it can
answer (the project number, the pool, the provider with its condition and
mapping, the service accounts); when it cannot -- no ``gcloud``, no
credentials -- there is no default, and ``--quiet`` refuses the question by
name. A starter's placeholders are no defaults either.
"""

from __future__ import annotations

import json
from typing import Any

from cs_image_system.base.bootstrap.facts import Facts, default_state_backend, first_runtime_name, real, runtime_of_type
from cs_image_system.base.bootstrap.questions import Answers, Question, Raw, Rendered, Secret, Section

MODULE = "bootstrap_gcp"
ISSUER = "https://token.actions.githubusercontent.com"
ABSENT = ("NOT_FOUND", "not found", "404", "does not exist")
READ_ROLES = "roles/compute.viewer"
WRITE_ROLES = "roles/compute.instanceAdmin.v1,roles/compute.storageAdmin,roles/iam.serviceAccountUser"


# ------------------------------------------------------------------ the project
def _runtime(facts: Facts) -> dict[str, Any]:
    return runtime_of_type(facts, "gcloud") or {}


def _describe(facts: Facts, *args: str) -> tuple[bool | None, dict[str, Any]]:
    """``(exists, record)``: True with what gcloud printed, False when the
    project SAID it is not there, None when it could not be asked."""
    code, out = facts.probe(["gcloud", *args, "--format=json"])
    if code == 0:
        try:
            data = json.loads(out[out.index("{"):out.rindex("}") + 1]) if "{" in out else {}
        except ValueError:
            data = {}
        return True, data if isinstance(data, dict) else {}
    if any(mark in out for mark in ABSENT):
        return False, {}
    return None, {}


def _project_number(facts: Facts, answers: Answers) -> str | None:
    project = answers.get("project")
    if not project:
        return None
    code, out = facts.probe(["gcloud", "projects", "describe", str(project), "--format=value(projectNumber)"])
    number = out.strip().splitlines()[0].strip() if code == 0 and out.strip() else ""
    return number if number.isdigit() else None


def _pool(facts: Facts, answers: Answers) -> tuple[bool | None, dict[str, Any]]:
    return _describe(facts, "iam", "workload-identity-pools", "describe", str(answers.get("pool")),
                     f"--project={answers.get('project')}", "--location=global")


def _provider(facts: Facts, answers: Answers) -> tuple[bool | None, dict[str, Any]]:
    if answers.get("pool_exists") is False:
        return False, {}                       # no pool, so no provider in it
    return _describe(facts, "iam", "workload-identity-pools", "providers", "describe", str(answers.get("provider")),
                     f"--project={answers.get('project')}", "--location=global",
                     f"--workload-identity-pool={answers.get('pool')}")


def _account_email(answers: Answers, key: str) -> str:
    return f"{answers.get(key)}@{answers.get('project')}.iam.gserviceaccount.com"


def _account_exists(key: str):
    def probe(facts: Facts, answers: Answers) -> bool | None:
        if not answers.get(key) or not answers.get("project"):
            return None
        return _describe(facts, "iam", "service-accounts", "describe", _account_email(answers, key),
                         f"--project={answers.get('project')}")[0]
    return probe


# -------------------------------------------------------------------- defaults
def _principal_default(facts: Facts, answers: Answers) -> str:
    """Which token attribute the bindings name: the repository's id (a name
    can be recycled, an id cannot) when the provider maps it and the id is
    known; the repository's name otherwise. An EXISTING provider decides by
    what it already maps."""
    has_id = bool(facts.repo_id)
    if answers.get("provider_exists"):
        mapping = (_provider(facts, answers)[1].get("attributeMapping") or {})
        return "repository_id" if has_id and "attribute.repository_id" in mapping else "repository"
    return "repository_id" if has_id else "repository"


def _condition_default(facts: Facts, answers: Answers) -> str | None:
    """The provider's attribute condition: an existing provider's own, kept
    verbatim (it may admit other repositories; it is read, never rewritten);
    for a new one, the guide's -- this repository and nothing else."""
    if answers.get("provider_exists"):
        exists, record = _provider(facts, answers)
        return str(record.get("attributeCondition") or "") if exists else None
    if answers.get("principal_attribute") == "repository_id" and answers.get("repo_id"):
        return f"assertion.repository_id == '{answers['repo_id']}'"
    return f"assertion.repository == '{answers['repository']}'" if answers.get("repository") else None


def _write_default(facts: Facts, answers: Answers) -> bool:
    """A WRITE account is needed only when CI performs on a GCE runtime: by
    default, when the tree's default runtime is one."""
    name = first_runtime_name(facts, prefer=())
    return any(r.get("name") == name and str(r.get("type", "")).lower() == "gcloud" for r in facts.runtimes)


def _gcs(facts: Facts, key: str) -> str:
    return real((default_state_backend(facts, "gcs") or {}).get(key)) or ""


def _bucket_exists(facts: Facts, answers: Answers) -> bool | None:
    return _describe(facts, "storage", "buckets", "describe", f"gs://{answers.get('state_bucket')}")[0]


def _labels_default(facts: Facts, answers: Answers) -> str:
    tags = _runtime(facts).get("tags") or {}
    return ",".join(f"{k}={v}" for k, v in sorted(tags.items()) if real(v)) if isinstance(tags, dict) else ""


def _split(text: Any) -> list[str]:
    return [s.strip() for s in str(text or "").split(",") if s.strip()]


def names_repository(condition: str, answers: Answers) -> bool:
    """Whether a condition's text names this repository, by name or by id."""
    text = str(condition or "")
    return bool(text) and (str(answers.get("repository") or "\0") in text
                           or (bool(answers.get("repo_id")) and str(answers["repo_id"]) in text))


UNASKABLE = "the project could not be asked: `gcloud` is absent or has no credentials"

QUESTIONS: tuple[Question, ...] = (
    Question("project", "The GCP project id", default=lambda f, a: real(_runtime(f).get("project_id")),
             help="the GCE runtime's `project_id` in cfg/runtime-builders.yml is unset or still the starter's placeholder"),
    Question("project_number", "The project's NUMBER (`gcloud projects describe <project> --format='value(projectNumber)'`)",
             default=_project_number, help=UNASKABLE),
    Question("repository", "The GitHub repository the identities trust, as owner/name", default=lambda f, a: f.repository,
             help="read from `git remote get-url origin` when the checkout has a GitHub remote"),
    Question("pool", "The workload identity pool's id", default="github"),
    Question("pool_exists", "Does that workload identity pool already exist (it is then read, not made)?", kind="bool",
             default=lambda f, a: _pool(f, a)[0], help=UNASKABLE),
    Question("provider", "The pool's GitHub provider id", default="github"),
    Question("provider_exists", "Does that provider already exist (it is then read, never rewritten)?", kind="bool",
             default=lambda f, a: _provider(f, a)[0], help=UNASKABLE),
    Question("principal_attribute", "Which token attribute the bindings name: the repository's id (it cannot be "
             "recycled) or its name", kind="choice", choices=("repository_id", "repository"), default=_principal_default),
    Question("repo_id", "The repository's numeric id (`gh api repos/<owner>/<repo> --jq .id`)",
             when=lambda a: a.get("principal_attribute") == "repository_id",
             default=lambda f, a: str(f.repo_id) if f.repo_id else None, help="`gh` is absent or not logged in"),
    Question("attribute_condition", "The provider's attribute condition (an existing provider's is shown as it "
             "stands and is not changed)", default=_condition_default, help=UNASKABLE),
    Question("production_branch", "The branch the WRITE account trusts (the perform job's)", default="main"),
    Question("read_account", "The READ-ONLY service account's id (GCP_SERVICE_ACCOUNT)", default="csis-github-readonly"),
    Question("read_account_exists", "Does the READ-ONLY service account already exist (it is then read, not made)?",
             kind="bool", default=_account_exists("read_account"), help=UNASKABLE),
    Question("read_roles", "Project roles the READ-ONLY account holds, comma-separated (add roles/file.viewer for "
             "Filestore, a storage role for bucket metadata)", default=READ_ROLES),
    Question("want_write", "Does CI perform on a GCE runtime (it then needs a WRITE service account)?", kind="bool",
             default=_write_default),
    Question("write_account", "The WRITE service account's id (GCP_APPLY_SERVICE_ACCOUNT)",
             when=lambda a: bool(a.get("want_write")), default="csis-github-apply"),
    Question("write_account_exists", "Does the WRITE service account already exist (it is then read, not made)?",
             kind="bool", when=lambda a: bool(a.get("want_write")), default=_account_exists("write_account"),
             help=UNASKABLE),
    Question("write_roles", "Project roles the WRITE account holds, comma-separated (instances, images, disks, and "
             "acting as the runner service account)", when=lambda a: bool(a.get("want_write")), default=WRITE_ROLES),
    Question("state_bucket", "The GCS state bucket, when this tree keeps its state in GCS (empty otherwise)",
             default=lambda f, a: _gcs(f, "bucket")),
    Question("state_prefix", "The state prefix within that bucket", when=lambda a: bool(a.get("state_bucket")),
             default=lambda f, a: _gcs(f, "prefix").strip("/") or None,
             help="the default GCS backend's `prefix` in cfg/state-backends.yml"),
    Question("state_bucket_exists", "Does that bucket already exist?", kind="bool",
             when=lambda a: bool(a.get("state_bucket")), default=_bucket_exists, help=UNASKABLE),
    Question("labels", "Labels for what this root makes, as k=v,k=v (empty for none)", default=_labels_default),
)


def render(answers: Answers) -> Rendered:
    project = str(answers["project"])
    want_write = bool(answers.get("want_write"))
    attribute = str(answers["principal_attribute"])
    principal_value = str(answers.get("repo_id") or "") if attribute == "repository_id" else str(answers["repository"])
    condition = str(answers.get("attribute_condition") or "")
    provider_exists = bool(answers["provider_exists"])
    names = ("project", "project_number", "pool", "pool_exists", "provider", "provider_exists", "principal_attribute",
             "production_branch", "read_account", "read_account_exists")
    bools = {"pool_exists", "provider_exists", "read_account_exists"}
    described = {
        "project": "the GCP project id", "project_number": "the project's number",
        "pool": "the workload identity pool's id", "pool_exists": "the pool already exists (read, not made)",
        "provider": "the pool's GitHub provider id",
        "provider_exists": "the provider already exists (read, never rewritten)",
        "principal_attribute": "the token attribute the bindings name: repository_id or repository",
        "production_branch": "the branch the WRITE account trusts",
        "read_account": "the READ-ONLY service account's id",
        "read_account_exists": "the READ-ONLY service account already exists (read, not made)",
    }
    variables = tuple((f"gcp_{n}", "bool" if n in bools else "string", described[n]) for n in names) + (
        ("gcp_principal_value", "string", "the value of that attribute: the repository's id, or its owner/name"),
        ("gcp_attribute_condition", "string", "the provider's attribute condition (used only when the provider is made)"),
        ("gcp_read_roles", "list(string)", "project roles the READ-ONLY account holds"),
        ("gcp_want_write", "bool", "CI performs on a GCE runtime: a WRITE service account is made or read"),
        ("gcp_write_account", "string", "the WRITE service account's id (empty when there is none)"),
        ("gcp_write_account_exists", "bool", "the WRITE service account already exists (read, not made)"),
        ("gcp_write_roles", "list(string)", "project roles the WRITE account holds"),
    )
    tfvars: dict[str, Any] = {f"gcp_{n}": (bool(answers[n]) if n in bools else str(answers[n])) for n in names}
    tfvars.update({
        "gcp_principal_value": principal_value,
        "gcp_attribute_condition": condition,
        "gcp_read_roles": _split(answers.get("read_roles")),
        "gcp_want_write": want_write,
        "gcp_write_account": str(answers.get("write_account") or "") if want_write else "",
        "gcp_write_account_exists": bool(answers.get("write_account_exists")) if want_write else False,
        "gcp_write_roles": _split(answers.get("write_roles")) if want_write else [],
    })
    backend = None
    if answers.get("state_bucket") and answers.get("state_bucket_exists"):
        backend = ("gcs", {"bucket": answers["state_bucket"],
                           "prefix": f"{str(answers['state_prefix']).strip('/')}/bootstrap"})
    by_hand = ["The network and the firewall rules: the team's, never modified by the system."]
    if provider_exists and not names_repository(condition, answers):
        by_hand.insert(0, f"The existing provider `{answers['provider']}` has the attribute condition `{condition or '(none)'}`, "
                          f"which does not name this repository (`{answers['repository']}`"
                          + (f", id {answers['repo_id']}" if answers.get("repo_id") else "")
                          + "): add it to the condition by hand, or the bindings made here admit nobody. The bootstrap "
                            "never rewrites a provider that exists, because other repositories may share it.")
    if not want_write:
        by_hand.append("No WRITE service account: `GCP_APPLY_SERVICE_ACCOUNT` is set to the READ-ONLY account's "
                       "address (CI never writes to a runtime it does not perform on), or delete those lines from "
                       "the `perform` job (CI_SETUP.md 3.4 step 4).")
    labels = {k: v for k, v in (p.split("=", 1) for p in _split(answers.get("labels")) if "=" in p)}
    return Rendered(
        module=MODULE,
        # `provider` is a reserved variable name inside a module: the module calls it provider_id
        module_args={**{{"provider": "provider_id"}.get(n, n): Raw(f"var.gcp_{n}") for n in names},
                     **{k: Raw(f"var.gcp_{k}") for k in ("principal_value", "attribute_condition", "read_roles",
                                                         "want_write", "write_account", "write_account_exists",
                                                         "write_roles")}},
        variables=variables,
        tfvars=tfvars,
        outputs=(
            ("gcp_workload_identity_provider", f"module.{MODULE}.workload_identity_provider",
             "the provider's full name: the GCP_WORKLOAD_IDENTITY_PROVIDER secret"),
            ("gcp_read_service_account", f"module.{MODULE}.read_service_account",
             "the READ-ONLY service account's address: the GCP_SERVICE_ACCOUNT secret"),
            ("gcp_write_service_account", f"module.{MODULE}.write_service_account",
             "the address CI may write as (the READ-ONLY one when there is no WRITE account): the GCP_APPLY_SERVICE_ACCOUNT secret"),
        ),
        required_providers={"google": {"source": "hashicorp/google", "version": ">= 5.0"}},
        provider_blocks=('provider "google" {\n  project = var.gcp_project   # the credentials: GOOGLE_OAUTH_ACCESS_TOKEN '
                         '(README.md, "Apply")\n}\n'),
        # The probes asked as the active `gcloud` account; terraform must act as
        # the same one. Application-default credentials are often something else
        # entirely -- on the reference machine they impersonate a runtime's
        # service account, which can read no IAM, and the first live plan failed
        # with 403 on every data source.
        apply_env=(("GOOGLE_OAUTH_ACCESS_TOKEN", "$(gcloud auth print-access-token)",
                    "your active `gcloud` account's token, which the google provider prefers over application-default "
                    "credentials (those may impersonate a runtime's service account that can read no IAM); it lasts "
                    "about an hour"),),
        secrets=(
            Secret("GCP_WORKLOAD_IDENTITY_PROVIDER", "output", "gcp_workload_identity_provider",
                   "the provider's full resource name, from the applied root"),
            Secret("GCP_SERVICE_ACCOUNT", "output", "gcp_read_service_account",
                   "the READ-ONLY service account's address, from the applied root"),
            Secret("GCP_APPLY_SERVICE_ACCOUNT", "output", "gcp_write_service_account",
                   "the address CI may write as, from the applied root"),
        ),
        by_hand=tuple(by_hand),
        notes=(
            f"project `{project}` (number {answers['project_number']}); the pool `{answers['pool']}` "
            + ("read (it exists)" if answers["pool_exists"] else "created")
            + f", its provider `{answers['provider']}` " + ("read (it exists, and is not rewritten)" if provider_exists
                                                             else f"created with the condition `{condition}`"),
            f"the READ-ONLY account `{answers['read_account']}` " + ("read (it exists)" if answers["read_account_exists"] else "created")
            + f", holding {', '.join(_split(answers.get('read_roles'))) or 'no project role'}; impersonated by "
            f"`attribute.{attribute}/{principal_value}`",
            (f"the WRITE account `{answers.get('write_account')}` "
             + ("read (it exists)" if answers.get("write_account_exists") else "created")
             + f", impersonated on `{answers['production_branch']}` alone") if want_write
            else "no WRITE account: CI does not perform on a GCE runtime",
            "every role and binding here is one member added; nothing existing is replaced",
            *((f"labels: {', '.join(f'{k}={v}' for k, v in sorted(labels.items()))} (service accounts carry no labels; "
               "kept for what later iterations make)",) if labels else ()),
        ),
        backend=backend,
    )


def wanted(facts: Facts) -> bool:
    """The tree uses GCP: it declares a GCE runtime or keeps its state in GCS."""
    return runtime_of_type(facts, "gcloud") is not None or default_state_backend(facts, "gcs") is not None


def gcp_section() -> Section:
    return Section(name="gcp", title="GCP", questions=QUESTIONS, render=render, wanted=wanted,
                   description="the workload identity pool and GitHub provider, the read-only and write service accounts, their bindings")
