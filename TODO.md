# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress**.

Open stages and their order: §37, then §41; §43 whenever convenient;
§19 and §30 wait on the operator's decisions.

Standing decisions (operator):

- The documentation describes what is; no document carries a commit hash;
  a landed stage is recorded by its squash message, not by a ledger or an
  archive entry.
- Publication is done: both repositories are public, each a single commit
  built from a redacted tree, with the pre-publication history private and
  archived. The identifiers (account id, project number, VPC, subnet and
  security-group ids, image ids, the state bucket, the Okta org and OPA
  team) are public by decision; the live rosters are real and encrypted to
  the four recipients; the fixture's people are synthetic.
- All terraform state stays in the AWS S3 backend by design; a GCS backend
  for the GCE roots and per-runtime networking validation are the very
  last priorities and are not stages; a session identity for the runtime
  session hook other than the operator's login key is deferred.
- No new GCP work unless a change is likely to make the existing GCP code
  fail; then the GCE cycle runs as the proof, on the operator's account,
  and is torn down. GCP is the operator's money.
- The release publish target is the tag until §41.
- §19 (the first real model image) stays planned by the operator's
  instruction; §30 (the contract package) is planned.

---

## 19. The first real model image, released and in use

**Why**: the system's stated purpose (EXPLORE "Systemic Purpose") is
images that are correct for a given HPC model, formally released, with
scientists logging in. The retrospective's warning still stands — "the
doorway got finished before the building": the fixture's playbooks are
placeholders (DESCRIPTION.md), the dask image installs dask and nothing
else, and no image has been used by anyone. Every mechanism the purpose
needs now exists: shell + ansible modifications with local mod tests,
in-bake and post-bake tests, declared releases, `require_released_builds`,
group ownership → OPA access (proven by `sft ssh` in stage 1), storage
attached by group. This stage spends them on one model, on AWS.

1. **USER — the model**: which one first (the groups are named for them:
   coops, stofs, secofs, tcmet); what its image must contain (packages,
   model source or binaries, data paths); what "correct" means as tests
   (a smoke run of the model, expected files and services); who its users
   are (the group's members); the instance size and the standing hours it
   may cost on the AWS account; its storage (the existing `mnt_data` /
   `efs-storage` / bucket, or new declarations).
2. **The image**: `basic-rh-10` on AWS plus an instance image owned by
   the model's group; real modifications — ansible for the stack, bash
   `ensure` for glue — idempotent and passing `just test-mods`; in-bake
   `tests:` and `tests.post_bake` running the model's smoke test;
   `release: {model: <name>}`.
3. **The instance(s)**: declared for the group with `image_policy: pinned`
   and `require_released_builds: true` (only a released build may pin);
   storage per the decision; launched through the gates on AWS (private
   subnet, no public IP; the existing network configuration untouched —
   standing constraint).
4. **Users in**: the group's members log in through the Okta gateway
   relay (`sft ssh`); evidence captured, the stage-1 shape.
5. **Operations, once**: the upgrade path exercised end to end (`upgrade
image` → re-bake → `upgrade instance` → gated replace) so the model's
   second release is a procedure, not a discovery; the standing cost noted
   for the AWS account.
6. Records: ledger, PLAN, OPERATIONS "a model image, end to end".
   Feature branch `feature/model-<name>`, squash-merged, kept.

## 30. The plugin contract is a package of protocols

**Why**: a plugin author should be able to write a plugin against ONE
package — `cs-image-system-contract` — and never import, let alone
subclass, the core's base classes. The base classes are the convenient
implementation of that contract, not the contract itself; a plugin that
satisfies the protocols structurally is a first-class plugin. That is the
operator's stated goal (2026-09-13) and it reverses the direction §29 had
taken (fold the protocols into the bases): the protocols are kept and made
real. Today the promise is not delivered: `base/protocols/` imports
`constants`, `registry` and the field helpers from the rest of `base`; a
plugin's own `pyproject.toml` depends on `cs-image-system-system` (the CLI
host); plugins import from ~60 core modules and ~106 names, of which ~24
are functions whose first argument is the live run context, reached
through the `GlobalTypeContext` singleton at ~50 sites; the mapper
dispatches on base-class identity; and two things already satisfy a
protocol structurally only by accident (`ProviderSpecificImage`, and every
`BuilderBase` at the registry's gate). Measured 2026-09-13 with the
per-plugin distance: `tf-s3-state-plugin` needs 7 core names,
`tf-ebs-instance-plugin` 42 plus 24 context reaches.

**Honest cost**, in three tiers: the two static tiers (models, behaviour)
are ~3–4 days of mostly mechanical work; the context interface is 1–2
weeks and is the part that makes an external plugin real; the proving
plugin 1–2 days. Call it three weeks, done as three branches.

1. **The package**: `packages/contract` → `cs_image_system.contract`, a
   workspace member with NO dependency on `base` or `system` (pydantic and
   `packaging` only); `base` depends on it, never the reverse, and a test
   asserts the import direction. It carries the constants protocols need
   (`VCT`, `FK_TARGET`, `DEFAULT`/`SELF`/`OOPS_DEFAULTS`),
   `CSIS_MODEL_CONFIG`, `fk_field`/`templated_field`, the lifecycle enums
   (`ExecutionLifecyclePhase`, `Lifecycle`, `LifecycleSpec`, `HookSet`) and
   the value types a plugin constructs (`Asset`/`AssetSet`,
   `ExecutableModel`, `CFExecutables`) — concrete data carriers are part
   of a contract; behaviour is not.
2. **Tier A — model protocols** (structural, with attribute declarations):
   `NameTyped` (`name`, `type_`, `description`, `aliases`, `global_id`,
   `get_classification`), `BuilderModel`, and one per builder kind
   (runtime, os, storage, image, instance, mod, group, user, state) with
   exactly the attributes the core reads. A plugin model is any pydantic
   dataclass under `CSIS_MODEL_CONFIG` that satisfies them; the `type`
   alias and `fk_field` metadata are the contract's, exported. The
   `ParentPropertyHolding` attribute (`_model_id`) is declared in the
   protocol and by each implementer — a protocol cannot carry a dataclass
   field, which is why it is copied at nine sites today; `base` offers a
   pydantic-dataclass mixin as the convenience, and the copies in the
   core's own models go through it.
3. **Tier B — behaviour protocols**: `PluginMetadata` (the seven
   properties; `AbstractPluginMetadata`'s `version` bug — it returns the
   metadata version — fixed on the way), `PluginArtifact`
   (`csis_name`/`csis_classifier`), and the builder surface: the six
   universal lifecycle hooks (`generate_items_{before,during,after}`,
   `get_commands_to_run_{before,during,after}`) as `Builder`, plus one
   protocol per kind for the ~60 domain hooks (`StorageBuilder`:
   `module_args`, `capability_type`, `attachment_cardinality`,
   `transition_actions`, `supports_archive`…; `RuntimeBuilder`: the 16
   query/session/dispose hooks; `GroupBuilder`, `ImageBuilder`,
   `InstanceBuilder`, `ModBuilder`, `UserBuilder`, `StateBuilder`). The
   protocols carry NO implementation (today `NameTypedProtocol` supplies
   `global_id` and a `get_classification` default; those bodies move to
   the base classes). `StateManagementRootProtocol` is dead — zero
   implementers — and is deleted.
4. **Tier C — the context protocol**, the expensive part: `RunContext`
   with the ~55 members plugins read (top: `meta_state`,
   `runtime_builders`, `os_builders`, `run_id`, `instances`, `images_map`,
   `generation_path`, `storage_builders`, `storages`, `dry_run`, …), with
   `MetaState` its own protocol (the mutable run records that the storage
   and instance builders write on both clouds); the ~24 context-first
   functions plugins import (`capabilities.*`, `lineage.*`,
   `launch_params.*`, `image_tests.*`, `storage_state.*`,
   `identity_attributes.*`, three from `commands.verify_instance`) either
   become methods of the protocol or are re-exported by the contract as
   functions typed against it. `GlobalTypeContext` implements it; the
   builder protocol receives the context by injection (`bind(ctx)`) so a
   plugin never constructs the singleton — the ~18 direct
   `GlobalTypeContext()` constructions in plugin code and the 33
   `_get_context()` calls go through it.
5. **The base classes implement the protocols** — `class NameTyped(…)`
   declares the protocol nominally as well, so pyright checks every base
   against it at definition time; a `contract.testing` module ships
   `assert_conforms(cls, protocol)` (signature-level, via `typing`
   introspection, stricter than `runtime_checkable`'s name-only check)
   and the core's tests run it over every base class and every built-in
   plugin. The two accidental structural implementers become deliberate:
   `ProviderSpecificImage` and `BuilderBase` conform by the same test.
6. **Runtime checks stay structural** and move to the contract's
   protocols: `loader.py` (`PluginMetadata`), `registry.py`
   (`NameTyped`, `PluginArtifact`), the orchestrator's marker dispatch
   (`SelfInjectedName`, `ParentPropertyHolding`, `SubItemOverride`) — all
   `runtime_checkable`, all name-only at runtime, all backed by step 5's
   conformance test so the looseness is not the only check. The mapper:
   `PydanticConverter` drops its base-class identity table (`_base_vcts`)
   and dispatches by `csis_classifier()` for any registered dataclass that
   satisfies `NameTyped` — the registry already resolves plugin models by
   type key.
7. **Plugins depend on the contract**: every plugin's `pyproject.toml`
   depends on `cs-image-system-contract` and, only where it truly uses a
   core utility, on `base` (the ~12 pure helpers — `render_module_call`,
   `hcl_expr`, `super_safe_name`, … — move to the contract or to
   `hashicorp-utils`, which is declared for what it is: a library five
   plugins use, not a plugin). The three undeclared dependencies
   (`tf-ebs`→`aws_runtime`, `aws-runtime`/`gcloud-runtime`→`dummy_plugin`)
   are declared or removed; the three private cross-plugin imports
   (`_groups`, `_public_read`, `_make_credentials`) get public names. No
   plugin depends on `system`.
8. **The proof — an external plugin**: a new workspace member
   `packages/contract-example-plugin` implementing one trivial storage (or
   runtime) plugin against `cs_image_system.contract` ONLY — a test greps
   its source for `cs_image_system.base` and fails on any hit; it is
   loaded by entry point, its model structures from a fixture YAML, and it
   participates in a dry `run --all` over a copy of the frozen fixture
   with its module call emitted. That is the acceptance; without it the
   contract is a claim.
9. Residue carried from §29: fix `RuntimeBuilderBase`'s anonymous inline
   TypeVar (it was never generic); the nine `_model_id` copies in the core
   go through the mixin; the four type-escape hatches caused by the
   protocol/base split (`builder_base.py:61`, `orchestrator.py:681`,
   `registry.py:86`, `os_builder_runtime_config.py:173`) are fixed, not
   repointed. Golden byte-identical at every branch; bar green; pyright at
   0 errors. Records: ledger; DESIGN's plugin-contract section rewritten
   around the package; OPERATIONS "writing a plugin". Branches
   `feature/contract-package` (steps 1–3, 5–7),
   `feature/contract-context` (step 4), `feature/contract-example`
   (step 8), each squash-merged, kept.

## 37. The real run on `main`

**Why**: the operator's CI model is "branches verify, `main` applies". The
`live` job is half of it, and it is read-only. The other half is a run
with `--no-dry-run --commit` over the live configuration, whose
meta-state and emission land in the configuration repository: that is
what makes a merge to `main` an operation rather than a record. The
system needs no change for it — the run is the one an operator performs
by hand ([docs/OPERATIONS.md](docs/OPERATIONS.md)) — so the stage builds
the job, its identities and its scope.

**Where this stands**: the job, its pins and the manual are landed, and
every identity exists — twelve secrets, the write-capable role trusting
`main` alone, the push token scoped to the configuration repository.
Nothing is left but the proofs, and they need one thing: `main` must
carry the job, because the write role refuses every other ref. Advancing
`main` is safe while nothing has been proven, since apply mode now fails
at the gate rather than passing quietly, and the write-access check fails
before any bake. The first real run is then the operator's to trigger.

1. **DONE — scope, decided up front.** Nothing here is code; it is the set of
   decisions the rest of the stage implements, each one checkable today.
   1. **One runtime.** The job runs `run --all --only-runtime
      aws-east2-runtime`, the runtime the live images bake on. It never
      runs the GCE runtime, whose cycle stays a hand-run
      (`just cloud-cycle gcloud-east1`) under the GCP cost decision.
   2. **No write-capable GCP identity, ever.** The job keeps the
      read-only GCP identity the `live` job already uses, because the
      configuration load discovers the gcloud network. A GCE root that
      slipped into scope then fails at load instead of spending money.
   3. **What a real run actually does**, given the live `_config.yml`:
      ```sh
      grep -n 'apply_' ../cs-image-system-testconfig/cfg/_config.yml   # instances, storage, identity: all false
      ```
      With all three false and no `--apply-runtime`, the storage,
      instance and identity roots plan and gate only. What the run
      performs is the convergent bake of AWS images whose declaration
      changed (packer, in process, ephemeral build instances), the
      declared releases, retention disposals, and the meta-state commit.
   4. **What that excludes, and why.** Post-bake tests launch an instance,
      so they need `apply_instances`; they do not run in this first
      realisation. Letting the AWS roots apply (`--apply-runtime
      aws-east2-runtime`) is a later **USER** decision, taken only once
      the bake half has run unattended for a while.
   5. Record the four decisions in the stage's squash message, because
      they are the reason the job is shaped the way it is.
2. **DONE — the identities.** All three groups exist: the write-capable
   role and its policy, the Okta triple, and the push token. Three groups. None of them can be created
   by the system, and none of their values may ever be printed.
   1. **DONE — the write-capable AWS role**, `csis-github-apply`, trusting only
      `main` of the published repository. The trust document mirrors the
      read-only role's but pins the ref; both subject forms are needed
      because this organisation's OIDC subject embeds ids:
      ```sh
      O=infrastructurebuilder; R=cs-image-system-3
      ACCT=$(aws sts get-caller-identity --profile noaa --query Account --output text)
      ORG_ID=$(gh api orgs/$O --jq .id); REPO_ID=$(gh api repos/$O/$R --jq .id)
      cat > /tmp/apply-trust.json <<JSON
      {"Version":"2012-10-17","Statement":[{"Effect":"Allow",
       "Principal":{"Federated":"arn:aws:iam::$ACCT:oidc-provider/token.actions.githubusercontent.com"},
       "Action":"sts:AssumeRoleWithWebIdentity",
       "Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com",
         "token.actions.githubusercontent.com:sub":[
           "repo:$O/$R:ref:refs/heads/main",
           "repo:$O@$ORG_ID/$R@$REPO_ID:ref:refs/heads/main"]}}}]}
      JSON
      aws iam create-role --profile noaa --role-name csis-github-apply \
        --assume-role-policy-document file:///tmp/apply-trust.json \
        --description "GitHub Actions: real runs on main (bakes, releases, retention)"
      rm -f /tmp/apply-trust.json
      ```
      Note `ref:refs/heads/main` rather than the read-only role's `:*`:
      a branch other than `main` cannot assume it even by accident.
   2. **DONE — its permissions**, three statements, no more. The bake is packer's
      documented minimum; the state statement is scoped to this
      configuration's prefix alone; retention needs the deregister and
      delete:
      ```sh
      cat > /tmp/apply-policy.json <<'JSON'
      {"Version":"2012-10-17","Statement":[
        {"Sid":"BakeAndDescribe","Effect":"Allow","Resource":"*","Action":[
          "ec2:Describe*","ec2:RunInstances","ec2:StopInstances","ec2:TerminateInstances",
          "ec2:CreateKeyPair","ec2:DeleteKeyPair","ec2:CreateSecurityGroup","ec2:DeleteSecurityGroup",
          "ec2:AuthorizeSecurityGroupIngress","ec2:RevokeSecurityGroupIngress",
          "ec2:CreateImage","ec2:RegisterImage","ec2:DeregisterImage","ec2:CopyImage",
          "ec2:CreateSnapshot","ec2:DeleteSnapshot","ec2:CreateTags","ec2:DeleteTags",
          "ec2:ModifyImageAttribute","ec2:ModifyInstanceAttribute","ec2:GetConsoleOutput",
          "elasticfilesystem:Describe*","sts:GetCallerIdentity"]},
        {"Sid":"StatePrefix","Effect":"Allow",
         "Resource":["arn:aws:s3:::noaa-ioos-cloud-sandbox-tfstate",
                     "arn:aws:s3:::noaa-ioos-cloud-sandbox-tfstate/statefiles/csia-image-system-test/*"],
         "Action":["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject"]}]}
      JSON
      aws iam put-role-policy --profile noaa --role-name csis-github-apply \
        --policy-name csis-apply-bake-and-state --policy-document file:///tmp/apply-policy.json
      rm -f /tmp/apply-policy.json
      gh secret set AWS_APPLY_ROLE_ARN -R $O/$R \
        -b "arn:aws:iam::$ACCT:role/csis-github-apply"
      ```
      Deliberately absent: `iam:PassRole` (no instance profile is
      attached by a bake), every `ec2:*Volume*` and `ec2:*Subnet*` write
      (storage and networking are never applied here), and anything
      outside the state prefix. A later `--apply-runtime` decision adds
      what the instance roots need, as its own review.
   3. **DONE — the Okta secrets the terraform provider needs.** The `live` job
      never plans the identity roots, so it needs only the API key; a
      real run plans them, and the provider wants the full triple. They
      are already in `.envrc`:
      ```sh
      set -a; . ./.envrc; set +a
      for v in OKTA_API_CLIENT_ID OKTA_API_PRIVATE_KEY_ID OKTA_API_SCOPES; do
        printf '%s' "${!v}" | gh secret set "$v" -R $O/$R
      done
      ```
   4. **DONE — the push token** (operator, fine-grained, contents:write on
      the configuration repository alone, set as `CSIS_CONFIG_PUSH_TOKEN`
      on the system repository; twelve secrets now). Only a person can
      create one: GitHub has no API for it. The run commits into the configuration
      repository but never pushes; the job does. A fine-grained personal
      access token with **Contents: read and write on
      `cs-image-system-testconfig` only**, no other repository and no
      other permission, set as `CSIS_CONFIG_PUSH_TOKEN`. Create it in
      GitHub → Settings → Developer settings → Fine-grained tokens, then:
      ```sh
      gh secret set CSIS_CONFIG_PUSH_TOKEN -R $O/$R   # paste, then Ctrl-D
      gh secret list -R $O/$R                          # expect 12
      ```
   5. **DECIDED — `develop`**, which is what `live` reads and what every stage pushes; the job's checkout `ref:` and its push target are that branch. The question was: which configuration branch the job reads and pushes,
      `develop`, which is what `live` reads and what every stage pushes
      (recommended), or the configuration's own `main`. Whichever is
      chosen, the job's checkout `ref:` and its push target are that one
      branch, and the answer goes in the job's comment.
3. **DONE — the job.** One new job in [.github/workflows/ci.yml](.github/workflows/ci.yml),
   on `feature/ci-apply-on-main`.
   1. **Its trigger and its mode.** The workflow gains a
      `workflow_dispatch` input so the plumbing can be exercised without
      applying anything:
      ```yaml
      on:
        workflow_dispatch:
          inputs:
            mode:
              description: dry enumerates; apply performs (honoured only on main)
              type: choice
              options: [dry, apply]
              default: dry
      ```
   2. **Its guard and its lock.** `apply` runs after `live`, only on
      `main`, and never twice at once against one state:
      ```yaml
        apply:
          needs: live
          if: github.ref == 'refs/heads/main'
          concurrency: {group: apply-live, cancel-in-progress: false}
          permissions: {id-token: write, contents: read}
          runs-on: ubuntu-latest
      ```
   3. **Its preparation** repeats `live`'s, step for step, with two
      differences: the role is `AWS_APPLY_ROLE_ARN`, and the Okta triple
      joins the environment. Everything else — the two checkouts side by
      side, the `[noaa]` profile shim, the tool installation and the
      pinned paths — is copied verbatim, because a divergence between the
      two jobs is a defect waiting to happen.
   4. **The run itself**, one line, and the only place in the workflow
      that carries `--no-dry-run`:
      ```yaml
            - name: The real run over the live configuration
              working-directory: cs-image-system-3
              run: just cli --no-dry-run run --all --commit --only-runtime aws-east2-runtime
      ```
      With `mode: dry` the flag is omitted, so the same job enumerates
      instead of performing.
   5. **The push**, which the run never does. A non-fast-forward is a
      loud failure, never a force, because it means a person committed to
      the configuration while the run was in flight:
      ```yaml
            - name: Push what the run committed
              working-directory: cs-image-system-testconfig
              run: |
                git log --oneline -1
                git push "https://x-access-token:${{ secrets.CSIS_CONFIG_PUSH_TOKEN }}@github.com/infrastructurebuilder/cs-image-system-testconfig" HEAD:develop
      ```
   6. **The post-condition**: `just cloud-preflight`, so the job fails if
      the records and the clouds disagree after the run.
   7. **The skip lines.** The gate step gains the new secrets, each with
      its own `SKIPPED` line, so a missing identity reads as a reason
      rather than a stack trace.
4. **DONE — the pins**, in [tests/test_v2_ci_workflow.py](tests/test_v2_ci_workflow.py).
   Each is one assertion, and each would have caught a real mistake.
   1. `live` stays read-only: no `--no-dry-run`, no `--commit`.
   2. `apply` is the only job that carries either.
   3. `apply`'s condition names `refs/heads/main`.
   4. `apply` declares `concurrency.group` and does not cancel in progress.
   5. `apply` names `AWS_APPLY_ROLE_ARN`, never `AWS_ROLE_ARN`.
   6. No `GCP_APPLY_*` secret appears anywhere in the workflow.
   7. `apply`'s run line carries `--only-runtime aws-east2-runtime`, so a
      scope regression fails the bar rather than a cloud account.
5. **DONE — cost, in writing**, in the manual's CI section.
   1. **No CI run can leave a billable GCP resource standing**, because
      the job holds no identity that could create one. That is a
      structural guarantee, not a promise.
   2. **On AWS a run may leave what convergence baked**: an AMI and its
      snapshot, cents a month each, until retention disposes them.
   3. **The first `main` run is reported** with its run id and exactly
      what it baked, released, disposed and committed.
6. **Proof**, in three stages, cheapest first. The first waits on `main` carrying the job; the third is the operator's to trigger.
   1. **The plumbing, without applying.** A dispatch off `main` cannot do
      it: the write role trusts `ref:refs/heads/main` alone, so AWS
      refuses the assume and the job fails at the credentials step. That
      refusal is itself worth having — it proves the trust is as narrow as
      intended — but the dry proof has to run where the role is trusted.
      So: `main` first carries the job, which is safe while the push token
      is absent, since apply mode then fails at the gate without touching
      anything; then a dispatch on `main` in `dry` mode enumerates with
      every identity in play.
      ```sh
      git push origin develop:main          # main carries the job
      gh workflow run ci.yml -R $O/$R --ref main -f mode=dry
      gh run watch -R $O/$R "$(gh run list -R $O/$R --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
      # then read the step conclusions, never just the job's:
      gh run view <id> --json jobs -q '.jobs[] | select(.name=="apply") | .steps[] | "\(.conclusion) \(.name)"'
      ```
   2. **DONE — the push path, without pushing.** The job proves write
      access with `git push --dry-run` before the run step, so a token
      that is missing, empty or under-scoped stops the job rather than
      being discovered after a bake has spent money. It runs in dry mode
      too, whenever a push credential is present, which makes it the
      cheapest check of the token there is.
   3. **The first real run** happens at the next merge to `main`. Watch
      it, then check the configuration repository received exactly one
      commit and that `just cloud-preflight` is clean locally.
7. **Records.**
   1. The squash message carries step 1's four decisions and what the
      first run did.
   2. **DONE** — [docs/OPERATIONS.md](docs/OPERATIONS.md) gained the third job in its
      CI section, its secrets in the table with the Job column filled in,
      and step 5's cost sentences.
   3. This section is removed from the worksheet.
   4. Feature branch `feature/ci-apply-on-main`, squash-merged, kept. Two
      days, most of it the USER identities and watching the first run.

## 41. Releases publish to an index through `uv publish`

**Why**: `just release <version>` ends at an annotated tag and `dist/`
(the fourteen workspace packages, `uv build --all-packages`); its publish
leg exists but runs only with `UV_PUBLISH_URL` set, which nobody sets —
§39.2 decided 2026-09-15 that the tag is the release until this stage. A
tag is a source of truth, not a distribution: a second operator, CI, or a
plugin author writing against §30's contract installs from an index, and
a published version is immutable in a way a tag is not. This stage picks
the index and makes the leg real, at the endpoint `uv publish
--publish-url` (`UV_PUBLISH_URL`) takes. It depends on no other stage; if
the index is PyPI it follows §40.

1. **USER — the index.** Two shapes fit the endpoint: (a) **AWS
   CodeArtifact**, a PyPI-format repository in the account already in
   use — free tier 2 GB stored and 100k requests a month, cents beyond;
   authenticated with `aws codeartifact get-authorization-token` (twelve
   hours), so the operator's SSO session and CI's federated role both
   reach it with no long-lived secret; usable while the repositories are
   private and after — the recommendation. (b) **PyPI** once the
   repositories are public (§40), with trusted publishing from GitHub
   Actions (OIDC, no token at all; the fourteen `cs-image-system-*` names
   must be free there). GCP Artifact Registry is out by the GCP decision.
   For (a): one domain, one repository, and an external connection to
   `pypi` so a consumer resolves the packages' dependencies from the same
   index (otherwise `--extra-index-url`).
2. **A `publish` recipe, split out of `release`**: `just publish <version>`
   uploads `dist/` for that version only (`dist/` is cleaned before
   `just build` — today `uv publish dist/*` would upload every stale
   wheel left from an earlier version), with `--check-url` so a re-run
   after a partial failure skips what is already there; the index URL is
   the Justfile's default (`publish_url := env("UV_PUBLISH_URL", "<the
   decided index>")`), the credential comes from the environment
   (`UV_PUBLISH_TOKEN`, or for CodeArtifact `UV_PUBLISH_USERNAME=aws` and
   the token as `UV_PUBLISH_PASSWORD`) and is never in the Justfile.
3. **`release` publishes, and cannot half-release**: the credential and
   the index are probed BEFORE the version bump (today the publish leg is
   the last step, after the commit and the tag, so a failure there leaves
   a tagged, unpublished release); with them present `release` ends with
   `just publish`, without them it refuses up front — the SKIPPED path
   goes, since the target is decided. The contract test's needles
   (`tests/test_v2_justfile_contract.py:66`: `uv publish`,
   `UV_PUBLISH_URL`, `SKIPPED`) follow.
4. **CI publishes the tag**: a `publish` job in `.github/workflows/ci.yml`
   on `push` of a `v*` tag — `just init`, the federated identity (the
   read-only AWS role gains `codeartifact:GetAuthorizationToken`,
   `codeartifact:PublishPackageVersion` and `codeartifact:ReadFromRepository`
   on that one repository; or PyPI's trusted publisher), `just publish
   <tag>`. The operator's flow stays `just release <v>` then `git push
   --follow-tags`; the push is what publishes, and a local publish is the
   fallback when CI cannot. The workflow test pins that only this job
   runs `uv publish` and only on a tag.
5. **Consumers**: the index declared for installs in the root
   `pyproject.toml` (`[[tool.uv.index]]`, credentials via
   `UV_INDEX_<NAME>_USERNAME`/`_PASSWORD`), and OPERATIONS gains
   "installing a release": the two commands a stranger with access needs.
   Proof from a clean virtualenv on a machine that is not the operator's:
   `uv pip install --index-url <index> cs-image-system-system==<version>`,
   then `cs-image-system --help` and `cs-image-system decrypt` run.
6. **USER — the first version**: every package is `0.1.0` today and
   nothing has been published; the first `just release` after this stage
   publishes a version that can never be replaced, so it runs after a
   green `full-test` with docker (the recipe requires it) and on a clean
   live configuration.
7. Records: ledger; OPERATIONS "CI shape" (the fourth job) and the release
   paragraph; §16's open item closed for good. Feature branch
   `feature/publish-index`, squash-merged, kept. A day, plus the USER
   decision; the CodeArtifact setup is a dozen CLI commands.

## 43. Hygiene bundle II: the small things noted since §39

**Why**: each of these was found while doing something else between
2026-09-15 and 2026-09-16 and left alone because it was not that stage's
business. None is large; together they are a day. Each item lands with
its own proof, in one branch, and the golden may move where an item says
so. Whenever convenient; nothing else waits on it.

1. **A run commits no run-local file.** The live configuration tracks
   `generated/run-summary.json` and `generated/state-report.json` (four
   run-local files in all; `meta-state/runs.yaml` and
   `generated/final_execution.sh` are records and stay). The strict query
   rewrites the report outside any run, so every `just cloud-preflight`
   dirties the checkout and `publish-tree` rightly refuses it (found in
   §40.2). The run's commit pathspecs exclude the two files, the emitted
   ignore policy names them, and one dry `--commit` run removes them from
   the sibling's index (pushed). Proof: `just cloud-preflight` leaves
   `git status` clean; config-drift current.
2. **A modification that declares only `config:` is refused.** Two
   fixture and live items (`dask-setup2`, `data-science-workstation-two`
   on `imgfile-basic-dask-two`) carry config keys and no playbook or
   script; the ansible builder emits one provisioner per playbook, so they
   render nothing and only log a warning, while lineage, the on-image
   bundle and the modification tests all record them as present. Decision
   (recommended): a modification item with neither `playbooks` nor
   `script`/`scripts`/`ensure` fails validation with a message that names
   the item; the two items either gain a playbook that reads their config
   keys as variables or are deleted along with the two "stage 22.4
   REMOVED" comments beside them. **USER** chooses; either way a test pins
   the refusal, and the golden moves if the fixture's items change.
3. **The unused placeholder backend goes.** `cfg/state-backends.yml`
   declares `s3-east1` on `my-east1-tfstate-bucket` in both trees; no
   workspace binds to it and nothing references it. **USER** confirms it is
   a placeholder; then it is removed from both trees (the golden should not
   move: no workspace emits it).
4. **The looser `ci` recipe goes.** `just ci` (pyright non-blocking) is
   referenced by nothing since CI runs `just verify`, and the standing rule
   says such a target must not be the bar. Removed, with the contract test
   asserting it stays gone.
5. **Warnings the bar and the CLI print for no one**: pyright's
   `orchestrator.py:515` (a `@staticmethod` declared with `cls` — make it a
   classmethod or drop the parameter); the FK warning `golden-regen`
   prints for `gcloud-east1` against `os_builder_model` (a runtime name
   where an OS builder is expected in the fixture, or a wrong FK target —
   find which and fix it; the golden may move); `validate`'s per-tool "No
   valid version checker class found" and per-provider "No executable
   specified" lines (either implement the checkers the executables file
   promises or collapse them to one INFO line). Proof: the bar and
   `just cli validate` print none of them.
6. **One tofu process at a time, by construction.** A sibling run that
   overlapped the bar's tests failed on the shared plugin cache (ledger
   93). The suite's real-tofu tests use a private `TF_PLUGIN_CACHE_DIR`
   under their temporary directory, so the bar never contends with an
   operator's run; the tofu-using recipes (`config-drift`, `v2-dry-run`,
   `cloud-*`, `gce-*`) take a simple lock directory under
   `.tofu-plugin-cache/` and refuse with a clear message when another holds
   it. Proof: two concurrent `just config-drift` invocations, one refuses.
7. **CLI help that lags behaviour.** `--only-runtime`'s help names the
   bake surface only; the operating record says it has scoped the
   terraform roots too since 2026-09-10. Read the code, make the help say
   what the flag does, and add the missing test if the record is right.
   While there, every option's help is read once against its behaviour.
8. **`publish-tree` builds a tree with the wrong git identity.** The
   recipe's `git init` in a fresh directory takes the GLOBAL git identity,
   not the source repository's, so the tree's single commit can carry an
   address the operator does not push with. GitHub refused the first
   publication push for exactly that, and the commit had to be
   re-authored by hand. The recipe reads `user.name` and `user.email`
   from the source repository (falling back to the global values) and
   writes them into the new repository before committing; its test pins
   that a source repository with a distinctive `user.email` produces a
   commit carrying it.
9. **A secret that exists but is empty reads as absent, and the job
   passes.** The `live` job skipped every step across three runs on the
   published repository and reported success each time, because
   `OKTA_API_PRIVATE_KEY` had been set from a checkout where the file
   `.envrc` reads it from was missing: the secret existed and its value
   was the empty string. The gate is right to skip when nothing is
   configured, but it cannot tell that from configured-and-broken, and a
   reader of the job's conclusion cannot either. The `apply` job now
   fails rather than skips when a real run is asked for, and the same
   distinction belongs in `live`: a gate item whose secret exists but is
   empty is a failure, not an absence. While here, make `just preflight`
   report the same way, and never read a job's conclusion as proof that
   its steps ran.
10. Records by whatever convention is current when this lands. Feature
   branch `feature/hygiene-two`, squash-merged, kept. A day.
