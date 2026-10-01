# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The GitHub section (CI_SETUP.md section 3.2 and 3.7): the repository's
default branch, the ruleset that protects the production branch while
letting ``github-actions[bot]`` push the records ``perform`` writes, the
Actions permissions, the Actions variables that are not secret, and the
script that sets the secrets from files the interview named."""

from __future__ import annotations

from .facts import Facts, first_runtime_name, runtime_region
from .questions import Answers, Question, Raw, Rendered, Secret, Section

MODULE = "bootstrap_github"

#: Every secret the starter workflow's gates read (CI_SETUP.md 3.7). In
#: iteration one each comes from a file; the clouds' sections (later
#: iterations) turn the ARNs and addresses into outputs of the applied root.
SECRETS: tuple[Secret, ...] = (
    Secret("AWS_ROLE_ARN", "file", comment="the READ-ONLY AWS role's ARN (CI_SETUP.md 3.3)"),
    Secret("AWS_APPLY_ROLE_ARN", "file", comment="the WRITE AWS role's ARN (3.3)"),
    Secret("GCP_WORKLOAD_IDENTITY_PROVIDER", "file", comment="the provider's full resource name (3.4)"),
    Secret("GCP_SERVICE_ACCOUNT", "file", comment="the READ-ONLY service account's address (3.4)"),
    Secret("GCP_APPLY_SERVICE_ACCOUNT", "file", comment="the service account that may write (3.4)"),
    Secret("OKTA_API_PRIVATE_KEY", "file", comment="the okta provider's private key, PEM (3.5)"),
    Secret("TF_VAR_KEY", "file", comment="the OPA service user's key (3.5)"),
    Secret("TF_VAR_SECRET", "file", comment="the OPA service user's secret (3.5)"),
    Secret("CSIS_CONFIG_IDENTITY", "file", comment="CI's age identity, the whole file (3.6)"),
)


def _perform_default(facts: Facts, answers: Answers) -> str | None:
    return first_runtime_name(facts)


def _region_default(facts: Facts, answers: Answers) -> str:
    return runtime_region(facts, answers.get("perform_runtime")) or ""


QUESTIONS: tuple[Question, ...] = (
    Question("repository", "The GitHub repository, as owner/name", "text",
             default=lambda f, a: f.repository, var="github_repository",
             help="read from `git remote get-url origin` when the checkout has a GitHub remote"),
    Question("default_branch", "The default branch, where people push", "text",
             default=lambda f, a: f.default_branch or "develop", var="github_default_branch"),
    Question("production_branch", "The branch the perform job runs on", "text", default="main",
             var="github_production_branch"),
    Question("protect_production", "Protect the production branch with a ruleset (no deletion, no force "
             "push; github-actions[bot] may still push the records)?", "bool", default=True,
             var="github_protect_production"),
    Question("perform_runtime", "PERFORM_RUNTIME: the runtime the perform job bakes, releases and applies "
             "retention on", "text", default=_perform_default,
             help="a `name:` from cfg/runtime-builders.yml; none could be read"),
    Question("guard_runtime", "GUARD_RUNTIME: a runtime CI must never bake on (empty for none)", "text",
             default=""),
    Question("aws_region", "AWS_REGION: the region of the AWS runtime (empty in a GCE-only tree)", "text",
             default=_region_default),
    Question("secrets_dir", "The directory holding one file per secret, named after the secret, that "
             "set-secrets.sh reads (never committed)", "path", default="_uncommitted/secrets",
             help="a path relative to the repository root"),
)


def render(answers: Answers) -> Rendered:
    repository = str(answers["repository"])
    owner = repository.split("/", 1)[0]
    variables = {k: v for k, v in (("PERFORM_RUNTIME", answers.get("perform_runtime")),
                                   ("GUARD_RUNTIME", answers.get("guard_runtime")),
                                   ("AWS_REGION", answers.get("aws_region"))) if v}
    return Rendered(
        module=MODULE,
        module_args={
            "repository": Raw("var.github_repository"),
            "default_branch": Raw("var.github_default_branch"),
            "production_branch": Raw("var.github_production_branch"),
            "protect_production": Raw("var.github_protect_production"),
            "variables": Raw("var.github_actions_variables"),
        },
        variables=(
            ("github_owner", "string", "the repository's owner, for the github provider"),
            ("github_repository", "string", "the repository as owner/name"),
            ("github_default_branch", "string", "the default branch, where people push"),
            ("github_production_branch", "string", "the branch the perform job runs on"),
            ("github_protect_production", "bool", "a ruleset on the production branch: no deletion, no force push"),
            ("github_actions_variables", "map(string)", "Actions variables that are not secret"),
        ),
        tfvars={
            "github_owner": owner,
            "github_repository": repository,
            "github_default_branch": answers["default_branch"],
            "github_production_branch": answers["production_branch"],
            "github_protect_production": bool(answers["protect_production"]),
            "github_actions_variables": variables,
        },
        outputs=(
            ("github_repository_id", f"module.{MODULE}.repository_id", "the repository's numeric id (the one trust conditions pin)"),
            ("github_repository_node_id", f"module.{MODULE}.node_id", "the repository's node id"),
        ),
        required_providers={"github": {"source": "integrations/github", "version": ">= 6.0"}},
        provider_blocks='provider "github" {\n  owner = var.github_owner   # the token: GITHUB_TOKEN, or `gh auth token`\n}\n',
        secrets=SECRETS,
        by_hand=(
            "The nine secrets' VALUES: one file per secret under the secrets directory "
            f"(`{answers.get('secrets_dir')}`, never committed), then `bash set-secrets.sh` (CI_SETUP.md 3.7).",
            "The OPA workload connection and role (CI_SETUP.md 3.5 steps 1-2 and 4-6): the oktapam provider has no workload resources.",
            "The age identity for CI (CI_SETUP.md 3.6): `age-keygen`, the public key into encryption.recipients, `reencrypt`.",
            "The values in `.github/workflows/ci.yml` still marked REPLACE-ME: PERFORM_RUNTIME, GUARD_RUNTIME and AWS_REGION "
            "are set as Actions variables by this root, but the workflow reads its own literals until a release makes it read `vars`.",
        ),
        notes=(
            f"the repository `{repository}`: default branch `{answers['default_branch']}`, perform on "
            f"`{answers['production_branch']}`" + (" (protected by a ruleset the Actions app bypasses)"
                                                    if answers["protect_production"] else " (unprotected)"),
            "Actions enabled for all actions; workflow permissions stay read-only (the workflow asks for what each job needs)",
            "Actions variables: " + (", ".join(f"{k}={v}" for k, v in variables.items()) or "none"),
        ),
    )


def github_section() -> Section:
    return Section(name="github", title="GitHub", questions=QUESTIONS, render=render,
                   description="the repository's branches, protection, Actions permissions and variables; the secrets script")
