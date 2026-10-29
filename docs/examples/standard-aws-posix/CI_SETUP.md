# Setting up CI for a configuration repository, from scratch

This guide takes a configuration repository written by `cs-image-system
init-config` (or copied from a starter tree) from "it validates on my
machine" to "its CI proves it, records it and performs on `main`". It is
the same text in every starter tree and in the release; the system's
tests hold its secrets table to the workflow the release ships, so the
names below are the names the workflow reads. It was walked from nothing
twice between 2026-10-05 and 2026-10-14, on `standard-aws` and
`standard-aws-posix` (stage 65), and says what that found.

Every value that is yours appears as a placeholder: `<owner>` and
`<repo>` for the repository, `<account-id>` and `<region>` for AWS,
`<project>` and `<project-number>` for GCP, `<team>` for the Okta
Privileged Access (OPA) team. Nothing here is a credential, and nothing
you type while following it should end up in the repository: secrets go
into the CI system's secret store and nowhere else.

There is one section per CI system. GitHub is complete. GitLab is not
written yet.

## 1. What this repository is

A **configuration repository**: the declarations one team's environment
is built from (`cfg/`, `groups/`, `storages/`, `images/`, `instances/`),
the emission the system generates from them (`generated/`), and the
system's records of what exists (`meta-state/`). The system itself is not
in it: it is installed from a release (`uv tool install cs-image-system`),
and `.csis-version` names the release this repository was written by and
that CI installs. The parts the release owns (the `Justfile`, the
workflows, the public-safe hook, `.gitignore`, `tfmodules/`, this file)
are refreshed after an upgrade with `cs-image-system init-config .
--force`; the YAML is always yours.

What each file and field means is in the system's
[configuration reference](https://github.com/infrastructurebuilder/cs-image-system-3/blob/develop/docs/CONFIGURATION.md);
how a person works with such a repository day to day is its
[daily driver](https://github.com/infrastructurebuilder/cs-image-system-3/blob/develop/DAILY_DRIVER.md);
the operating manual, section 3, describes the workflow job by job.

## 2. Before CI

Set CI up only for a tree that already validates by hand. CI adds
federated identities and secrets; it adds no new rule, so a tree that
fails `just validate` on your machine fails the same way in CI, only
further from you.

1. The release installed and on `PATH` (`uv tool install
   cs-image-system==$(cat .csis-version)`; a development version comes
   from TestPyPI: add `--index-url https://test.pypi.org/simple/
   --extra-index-url https://pypi.org/simple/ --index-strategy
   unsafe-first-match`, so only the pinned `.dev` packages come from
   TestPyPI and everything else from PyPI).
2. `just init`: the public-safe hook, the plugin cache, a line naming the
   release it found (`init: cs-image-system <version> ready against
   <root>`; a release of 0.1.3 or before has no `--version`, and the line
   gives the bare name), and a line saying which command a run's
   callbacks will find. A run's own steps and the runner scripts call the command back
   by its bare name, so it must be on `PATH`: a release installed with
   `uv tool install` is; `CSIS="uv run cs-image-system"` puts its venv on
   the child's `PATH`; a `CSIS` that names a path (a development checkout)
   is put first on `PATH` by the `Justfile` itself.
3. Your own sessions for every runtime the tree declares (an AWS profile,
   GCP application-default credentials), the Okta and OPA credentials in
   your shell, and `CSIS_CONFIG_IDENTITY` pointing at your age identity:
   daily driver, section 1.
4. `just preflight`, then `just validate`, then `just dry`: all green.
5. The tree committed and pushed, with every `REPLACE-ME` in the YAML
   replaced and the starter's TEST age identity replaced by your own
   (daily driver, section 1.9, step 2).

## 3. GitHub

### 3.0 The bootstrap

Most of sections 3.2 to 3.7 can be generated instead of clicked. From the
repository root, with the release installed:

```sh
just bootstrap            # the interview: each question shows its default; --quiet takes them all
```

It loads no configuration (the sessions and federation it makes may not
exist yet); it reads the checkout (`git remote`, `gh api` for the ids when
`gh` is logged in) and the raw `cfg/*.yml` for its defaults, asks whether
you want each section, writes the answers to `bootstrap.yaml` at the root
of the tree, and generates `generated/bootstrap/`: one root module calling
`tfmodules/bootstrap_<section>`, `bootstrap.auto.tfvars` with every answer
(so the apply needs nothing typed again), `set-secrets.sh`, and a README
saying what was generated and what is still yours. Both `bootstrap.yaml`
and the tfvars are committed on purpose -- they hold names, ids and
branches, never a secret value -- and every run regenerates the directory
from the answers, so `config-drift` judges it like the rest of the
emission and a clone needs no interview. Applying is your act, never a
run's:

Terraform acts as whoever your shell's credentials name, and which ones it
needs depends on the sections you wanted: `GITHUB_TOKEN` always,
`AWS_PROFILE` with the AWS section, `GOOGLE_OAUTH_ACCESS_TOKEN` with the
GCP section (application-default credentials are often another identity
entirely -- a runtime's service account that can read no IAM, say). The
GitHub token: `$(gh auth token)` works where `gh` is logged in through a
browser; on a machine without one, a fine-grained personal access token
scoped to this one repository with Administration (read and write: the
default branch, the ruleset, the Actions permissions), Variables (read
and write), Secrets (read and write, for `set-secrets.sh`) and Metadata
(read). Such a token answers the repository's own endpoints and not the
organisation's (section 3.2, step 4, says which form to use). It never
goes into a file the tree commits: an `.envrc` line, or a gitignored
file the `.envrc` reads. The
`bootstrap` command prints the exact `export` lines for your tree when it
finishes, and so does the "Apply" block of `generated/bootstrap/README.md`;
run them first, then:

```sh
cd generated/bootstrap && tofu init && tofu plan && tofu apply && cd ../..
bash generated/bootstrap/set-secrets.sh      # one file per secret under _uncommitted/secrets (or SECRETS_DIR), a directory git ignores; one it would track is refused
```

What the sections do today, and what stays by hand:

| Section | Terraform does | By hand, still |
| --- | --- | --- |
| GitHub (3.2, 3.7) | the default branch; a ruleset on the production branch that blocks deletion and force pushes (an ordinary push, which is all `perform` ever does, is unaffected, so no bypass is needed); Actions enabled with read-only workflow permissions; the Actions variables `PERFORM_RUNTIME`, `GUARD_RUNTIME`, `AWS_REGION` | the secret VALUES (one file each, then the script); the `REPLACE-ME` literals in `ci.yml`, until a release makes the workflow read `vars` |
| AWS (3.3) | the GitHub OIDC identity provider (read when it exists); the READ-ONLY and WRITE roles with the trust and permission documents of 3.3, the subject forms you chose, your bucket, prefix, region, account and instance profile filled in (a role that exists is ADOPTED by an `import` block, so its trust is maintained from then on, and every subject it already trusted that is not this repository's -- another repository sharing the role -- is KEPT unless you drop it at the prompt); the state bucket and the Session Manager instance profile only when the account lacks them; `AWS_ROLE_ARN` and `AWS_APPLY_ROLE_ARN` set by the script from the applied root's outputs | the network, which is yours and never modified; removing a hand-made inline policy from an adopted role once the plan is clean |
| GCP (3.4) | the workload identity pool and its GitHub provider (the mapping of 3.4 and a condition admitting this repository alone); the READ-ONLY service account with its project roles, and the WRITE one when CI performs on a GCE runtime; the `workloadIdentityUser` bindings (the write one on the production branch alone); the three GCP secrets set by the script from the applied root's outputs. What already exists is READ, never rewritten, and every role and binding is one member added | the network and firewall, which are yours; adding this repository to an EXISTING provider's condition when it does not name it (the README of the generated root says when) |
| Okta and OPA (3.5) | nothing: this section creates nothing, it CHECKS. It reads the OPA workload connection and role (present, active, requiring this repository, the role bound and pinned to the production branch, both named on the `okta-tf` group builder) and asks the Okta API services app for a token with its own key and scopes; each check that fails becomes its step of 3.5 in the generated README | creating and activating the connection and the role (a DevOps and a security admin, in the console); the services app and its scopes (the org's Okta admins); the OPA service user and its key pair |
| The age identity (3.6) | nothing: a key is made on your machine | `age-keygen`, `reencrypt`; the script sets the secret from the file |

Every "does it already exist?" question in the AWS and GCP sections is
answered by asking the account when you have a session (`aws iam
get-role`, `head-bucket` and the like, as the profile your runtime names;
`gcloud iam workload-identity-pools describe`, `service-accounts
describe` and the like, as your active `gcloud` account); with no
session the interview asks you, and `--quiet` REFUSES that question by
name rather than guess -- a wrong guess is a failed apply at best. A
starter's `REPLACE-ME` values and its example account id are no defaults
either: fill `cfg/runtime-builders.yml` and `cfg/state-backends.yml`
first, or answer at the prompt.

A question whose answer may be empty says `(answer none for none)`: an
empty line takes the default shown in brackets, so the word `none` is
how you decline it. The project roles of a service account that already
exists default to none. Whoever made the account granted what it holds,
and a grant this root makes sits in this root's state, so a `tofu
destroy` here would take it from every tree that reads the account
(two configurations reading one account were found holding the same
grant each, 2026-10-09). The generated README lists, under "What a
destroy would take that this root did not make", everything of that
kind: those grants, and an AWS role adopted by import, which the
destroy deletes outright.

The root's state follows the bucket. When the state bucket exists, the
root is bound to the tree's declared S3 backend at
`<state prefix>/bootstrap.tfstate`, like every other root. When the
bootstrap is what makes the bucket, the first apply keeps its state in
`terraform.tfstate` beside the root (never committed); then run `just
bootstrap` again -- the bucket now exists, so the root binds to it, and
the interview remembers that this root made the bucket and keeps managing
it (`state_bucket_managed`), so the second plan changes nothing about it
-- and `tofu init -migrate-state` in `generated/bootstrap`. A bucket that
stood before the root is read and never managed; a destroy of the root
takes a bucket it made, and the generated README says which it is.

Taking it down again is the reverse, and by hand, since no run ever
plans this root: stop CI first (`gh workflow disable ci.yml`, because the
roles are about to go), then `tofu -chdir=generated/bootstrap plan
-destroy -out=<file>`, read it, `apply <file>` (the GCP section needs
your own token as the apply did). The state bucket is NOT in the plan
when the bootstrap made it: the root's state moved into the bucket and
the bucket left the state (above), and every other root's state is in
it too. So it goes last, by hand, emptied version by version (`aws s3api
list-object-versions`, `delete-objects`, `delete-bucket`), after every
other root has been destroyed. The daily driver's section 4.1 has the
whole order.

### 3.1 The workflows this tree carries

`.github/workflows/ci.yml` has three jobs:

| Job | When | What it does | Holds |
| --- | --- | --- | --- |
| `verify` | every push and pull request | installs the release, parses the `Justfile`, runs `just public-safe` | no secret |
| `live` | pushes and the nightly schedule, never pull requests | validate, is the committed emission current, the strict state query, the modification tests under docker | the READ-ONLY identities |
| `perform` | `main` (or a dispatch asking to record) | the record, the guard on `GUARD_RUNTIME`, the performing run of `PERFORM_RUNTIME` under the WRITE identity and, still under it, the login proof, the closing record, the strict state query | the read-only identities, and the write identity for the performing step and the login proof after it |

`.github/workflows/opa-workload-probe.yml` is dispatch only: it presents
this repository's OIDC token to your OPA workload connection and stops
(section 3.5).

Replace every `REPLACE-ME` in `ci.yml` before the first push that should
run `live`:

| Value | Meaning |
| --- | --- |
| `PERFORM_RUNTIME` | the runtime the `perform` job bakes, releases and applies retention on (a `name:` from `cfg/runtime-builders.yml`) |
| `GUARD_RUNTIME` | a runtime CI must never bake on (for example one billed to a person), or empty for none; its emission may not change between two records, or `perform` fails before anything performs. The vendor publishing a newer image under a base with no build yet there is not a change: the guard names the move and passes (on 0.1.2 and before it failed) |
| `AWS_REGION` | the region of the AWS runtime (absent in a GCE-only tree) |
| `TF_VAR_REPLACE_ME_key`, `TF_VAR_REPLACE_ME_secret` | rename to `TF_VAR_<team>_key` and `TF_VAR_<team>_secret`, where `<team>` is the OPA team with every non-alphanumeric character as `_` (the `team:` on your group builder); the values come from the `TF_VAR_KEY` and `TF_VAR_SECRET` secrets, which keep those names |

`.csis-version` pins the release CI installs. Taking a new release is:
move the version in that file, run `cs-image-system init-config . --force`
with the new release to refresh the release-owned parts, review the diff,
commit.

The workflows also name the machine they run on (`runs-on:
ubuntu-24.04`), the version of every action they use, and the system's
runner image every job runs inside (`container: image:
ghcr.io/infrastructurebuilder/csis-ci:alma10-<date>`: AlmaLinux 10 with
every tool at a pinned version, the host's docker socket mounted for
the modification tests), so this tree's CI changes only when you take
a release, never at no commit. Nothing is installed on the runner any
more; what the image carries, and what any other CI runner would need,
is the system repository's `docs/CI_RUNNER.md`. The image is public and pulled
with no login. To run your own build of it instead -- a private one,
in your own registry -- set the repository variable
`CSIS_RUNNER_IMAGE` to its reference (Settings, Secrets and variables,
Actions, Variables), and, for a registry other than `ghcr.io`, the
variable `CSIS_RUNNER_IMAGE_USERNAME` and the secret
`CSIS_RUNNER_IMAGE_PASSWORD` (unset, the job logs in to `ghcr.io`
with its own token); every job reads them
(`${{ vars.CSIS_RUNNER_IMAGE || '<the release's image>' }}`), and taking
a release never touches them. An image in your own organisation's
GitHub registry needs neither: the job's own token pulls it (every
job's `permissions:` block says `packages: read`). How to build it, and
what it must carry, is the system repository's `docs/CI_RUNNER.md`; a
job that fails at "Initialize containers" with `denied` cannot read the
image it names (`docs/CI_RUNNER.md`, section 4).
GitHub withdraws an old runner image every couple of years, and an
action's major version when its Node.js goes; the runs' annotations say
so for months first. When they do, a newer release of the system
carries the move: take it as above. (Moving the names forward is the
system's maintainers' duty, and how is in the daily driver's section
9.1.)

### 3.2 The repository

1. **Branches.** `develop` is the default branch and where people push;
   `main` is what `perform` runs on. A repository made from nothing has
   no `main` on GitHub: the bootstrap sets the default branch and the
   ruleset, and `main` exists from the first push of it, `git push
   origin develop:main`, which is also the first `perform`. After it,
   merge `develop` into `main` to perform (a fast-forward push of the
   same form); the records `perform` writes are pushed back to `main`,
   and `develop` takes them with `git merge --ff-only origin/main`. If
   git made a `master` when the tree was initialised, delete it
   (`git branch -d master`, `git push origin --delete master`); nothing
   reads it.
2. **Actions permissions.** Settings, Actions, General: Actions allowed,
   and "Workflow permissions" may stay read-only, because the workflow
   asks for what each job needs (`id-token: write` for federation,
   `contents: write` on `perform` alone).
3. **Protecting `main`.** If `main` is protected, the protection must
   still let the `perform` job push its records with the job's own token
   (`github-actions[bot]`): allow that actor to bypass, or use a ruleset
   that exempts it. A refused push leaves the performing run's records
   unpushed, and the next run finds images nothing recorded.
4. **The two ids trust conditions pin.** A name can be recycled; an id
   cannot. Read them once and keep them beside you for sections 3.3 to
   3.5:

   ```sh
   gh api repos/<owner>/<repo> --jq .id          # <repo-id>
   gh api users/<owner> --jq .id                 # <owner-id>
   gh api orgs/<owner>/actions/oidc/customization/sub   # the org's subject template, if it has one
   gh api repos/<owner>/<repo>/actions/oidc/customization/sub   # the repository's own (use_default: true means the org's, or GitHub's)
   ```

   The organisation's endpoint answers `403` to a token scoped to one
   repository (section 3.0's fine-grained token); the repository's
   endpoint answers it, and its `use_default` says whether the
   repository follows the organisation's template.

   If your organisation customises the OIDC subject, the token's `sub`
   carries those ids (for example
   `repo:<owner>@<owner-id>/<repo>@<repo-id>:ref:refs/heads/main`); trust
   the form your tokens actually carry. A trust condition that expects
   the plain form refuses every token and says only "not authorized".

### 3.3 AWS

Skip this section for a tree with no AWS runtime and no S3 state backend.

**The OIDC identity provider**, once per account: IAM, Identity
providers, add an OpenID Connect provider with provider URL
`https://token.actions.githubusercontent.com` and audience
`sts.amazonaws.com`.

**The READ-ONLY role** (`AWS_ROLE_ARN`). Its trust policy admits this
repository on any ref:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": [
        "repo:<owner>/<repo>:*",
        "repo:<owner>@<owner-id>/<repo>@<repo-id>:*"
      ]}
    }
  }]
}
```

Keep only the subject forms your organisation's tokens carry (section
3.2, step 4). Its permissions are what a load, a dry run and the state
query read. A dry run never touches remote state (`tofu init
-backend=false`), so the role needs no access to the state bucket's
objects:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "Describe", "Effect": "Allow", "Resource": "*",
     "Action": ["ec2:Describe*", "elasticfilesystem:Describe*", "sts:GetCallerIdentity"]},
    {"Sid": "StorageReality", "Effect": "Allow", "Resource": "arn:aws:s3:::*",
     "Action": ["s3:GetBucketTagging", "s3:GetLifecycleConfiguration", "s3:GetBucketLocation"]}
  ]
}
```

Treat this as the starting point, not the proof: if the `live` job's
state query reports a storage `unavailable`, CloudTrail's denied event
names the action the role lacks.

**The WRITE role** (`AWS_APPLY_ROLE_ARN`). Its trust policy admits this
repository on `main` alone, so no branch, tag or pull request can hold it:

```json
"StringEquals": {
  "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
  "token.actions.githubusercontent.com:sub": "repo:<owner>/<repo>:ref:refs/heads/main"
}
```

(or the id-bearing form, as above). Its permissions are what a bake, a
release and retention on `PERFORM_RUNTIME` do. The emitted packer sources
reach the build instance through Session Manager (no public IP), so the
role starts sessions and passes the SSM instance profile:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "BakeAndDescribe", "Effect": "Allow", "Resource": "*", "Action": [
      "ec2:Describe*", "ec2:RunInstances", "ec2:StopInstances", "ec2:TerminateInstances",
      "ec2:CreateKeyPair", "ec2:DeleteKeyPair",
      "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress",
      "ec2:CreateImage", "ec2:RegisterImage", "ec2:DeregisterImage", "ec2:CopyImage",
      "ec2:CreateSnapshot", "ec2:DeleteSnapshot", "ec2:CreateTags", "ec2:DeleteTags",
      "ec2:ModifyImageAttribute", "ec2:ModifyInstanceAttribute", "ec2:GetConsoleOutput",
      "elasticfilesystem:Describe*", "sts:GetCallerIdentity"]},
    {"Sid": "StatePrefix", "Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
     "Resource": ["arn:aws:s3:::<state-bucket>", "arn:aws:s3:::<state-bucket>/<state-prefix>/*"]},
    {"Sid": "SessionManagerBake", "Effect": "Allow", "Action": "ssm:StartSession", "Resource": [
      "arn:aws:ec2:<region>:<account-id>:instance/*",
      "arn:aws:ssm:<region>::document/AWS-StartSSHSession",
      "arn:aws:ssm:<region>::document/AWS-StartPortForwardingSession"]},
    {"Sid": "SessionManagerSessions", "Effect": "Allow", "Action": ["ssm:TerminateSession", "ssm:ResumeSession"],
     "Resource": "arn:aws:ssm:<region>:<account-id>:session/*"},
    {"Sid": "SessionManagerDescribe", "Effect": "Allow", "Resource": "*",
     "Action": ["ssm:DescribeInstanceInformation", "ssm:GetConnectionStatus", "ssm:DescribeSessions"]},
    {"Sid": "BakeInstanceProfile", "Effect": "Allow", "Action": "iam:PassRole",
     "Resource": "arn:aws:iam::<account-id>:role/<ssm-instance-role>",
     "Condition": {"StringEquals": {"iam:PassedToService": "ec2.amazonaws.com"}}},
    {"Sid": "BakeInstanceProfileRead", "Effect": "Allow", "Action": "iam:GetInstanceProfile",
     "Resource": "arn:aws:iam::<account-id>:instance-profile/<ssm-instance-profile>"}
  ]
}
```

`<state-bucket>` and `<state-prefix>` are your `cfg/state-backends.yml`;
`<ssm-instance-profile>` is the runtime's `session_instance_profile` (or
`iam_instance_profile`). The WRITE role also carries the READ-ONLY
document above, as a second policy (`cs-image-system-write-reads`):
a performing run reads reality before it applies, and a write role
without those reads reported the S3 storage `unavailable` with
`AccessDenied` on `GetBucketTagging` on every `perform` (2026-10-14,
hygiene XII item 33). The lifecycles generate no IAM. These roles are
made once: either by the bootstrap (3.0), which writes exactly these
documents as terraform you apply, or by a person in the console as
described here. A role made before a release that changed a document
lags it until the bootstrap root is applied again; the state query says
`REFUSED` when that is what it met.

**Two traps, each with its symptom.**

- The runtimes name a profile (`credentials.profile_name`), and botocore
  ignores the environment's keys whenever a profile is named. The
  workflow therefore writes the federated keys into `~/.aws/credentials`
  under that profile's name ("Name the federated credentials as the
  configuration's profile"). If you rename the profile in the YAML, the
  step follows it; if the load says the profile was not found, that step
  did not run.
- A shell that expands `$VAR:word` (zsh treats `:r`, `:h` and others as
  modifiers) silently corrupts an ARN or a subject typed with a variable
  in it. Paste literal values, or quote with `${VAR}`.

### 3.4 GCP

Skip this section for a tree with no GCE runtime and no `gcs` state
backend.

1. **A workload identity pool and a GitHub provider:**

   ```sh
   gcloud iam workload-identity-pools create github --project=<project> --location=global
   gcloud iam workload-identity-pools providers create-oidc github \
     --project=<project> --location=global --workload-identity-pool=github \
     --issuer-uri=https://token.actions.githubusercontent.com \
     --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref" \
     --attribute-condition="assertion.repository_id == '<repo-id>'"
   ```

   The condition admits this repository and nothing else in any owner.
2. **The READ-ONLY service account** (`GCP_SERVICE_ACCOUNT`), with what a
   load and the state query read: `roles/compute.viewer` (the runtime
   discovers its network, images, disks), and, when the tree declares
   them, read access to its buckets' metadata and `roles/file.viewer` for
   Filestore. If the account already exists, the bootstrap grants it
   nothing by default (3.0 says why); name roles only when this tree is
   the one to hold them. Let the repository impersonate it:

   ```sh
   gcloud iam service-accounts add-iam-policy-binding <read-sa>@<project>.iam.gserviceaccount.com \
     --role=roles/iam.workloadIdentityUser \
     --member="principalSet://iam.googleapis.com/projects/<project-number>/locations/global/workloadIdentityPools/github/attribute.repository_id/<repo-id>"
   ```

3. **`GCP_WORKLOAD_IDENTITY_PROVIDER`** is the provider's full name:
   `projects/<project-number>/locations/global/workloadIdentityPools/github/providers/github`.
4. **The WRITE service account** (`GCP_APPLY_SERVICE_ACCOUNT`) is needed
   only when `PERFORM_RUNTIME` is a GCE runtime: the roles a bake on GCE
   uses (instances, images, disks, and acting as the runner service
   account), bound like the read-only one but with the principal set
   narrowed to `attribute.ref/refs/heads/main`. A tree that declares a
   GCE runtime but never performs on it (it is `GUARD_RUNTIME`, or
   another runtime is `PERFORM_RUNTIME`) has two choices: create the
   secret with the READ-ONLY account's address, since CI never writes to
   that runtime, or delete the `GCP_APPLY_SERVICE_ACCOUNT` lines from the
   `perform` job (its gate entry and the "the identity that may write"
   auth step).

### 3.5 Okta and Okta Privileged Access

**The Okta API services app** (for the `okta/okta` provider's user
lookups): key-based client authentication, the read scopes granted, the
`*.manage` scopes not granted, DPoP off. Its private key is the
`OKTA_API_PRIVATE_KEY` secret.

**The OPA service user's API key pair** (groups, policies, enrollment
tokens, the gid lookups, the state query): the `TF_VAR_KEY` and
`TF_VAR_SECRET` secrets, exported by the workflow under the team's names
(section 3.1).

**The workload connection and the workload role.** CI logs into the
machines the system launches the way a person does, through `sft ssh`
and a short-lived certificate, as an OPA **workload**: the runner presents
GitHub's OIDC token, OPA validates it against a **workload connection**,
maps it to a **workload role**, and the security policies the system
manages name that role. Two objects are made by hand, once, by a security
admin in the OPA console; do **not** create a security policy by hand:
the system manages one CI policy per group, a copy of the group's user
policy with the role as its only principal.

| Item | Value |
| --- | --- |
| GitHub Owner | `<owner>` |
| `repository` claim | `<owner>/<repo>` (this configuration repository: it is the one that logs in) |
| `repository_owner` claim | `<owner>` |
| JWKS URL | `https://token.actions.githubusercontent.com/.well-known/jwks` |
| Connection name, role name | yours to choose, for example `github-<repo>` and `<repo>-ci` |
| Token TTL | 1 hour |

1. **The connection, as a draft.** DevOps Administration, Workload
   connections, Create Workload Connection; type GitHub Actions; GitHub
   Owner `<owner>`; the name; TTL 1 hour; the JWKS URL if the form did
   not fill it; Required Claims `repository` Equals `<owner>/<repo>` and
   `repository_owner` Equals `<owner>`; no `ref` claim here. Create. Do
   not activate it yet.
2. **The role.** Security Administration, Workload roles: the name, the
   connection selected, no conditions yet. If the console will not let
   you add the connection, the account lacks the security-admin
   privilege the role needs.
3. **The names into the tree.** On the `okta-tf` group builder in
   `cfg/group-builders.yml`, beside `team:`: `workload_connection:
   <connection>` and `workload_role: <role>`. Commit, push, and run the
   identity lifecycle, which creates the per-group CI policies.
4. **The probe.** Actions, "OPA workload probe", Run workflow, with your
   names. Against a draft, OPA accepts this run's token and issues one
   in reply, which the probe reports and discards (`connection <name>:
   accepted this run's token and issued one`); the log shows the
   token's claims and the client's verdict. Green here is the proof the
   claims match. Nothing logs in until step 5: the system's own login
   proof refuses a draft connection. The probe's second line, `role
   <name>: granted` / `not granted` / `not judged`, says whether the
   token it was issued CARRIES the role, judged by resolving a standing
   machine of a managed group as the workload; before a machine stands
   it says `not judged`, and it is what step 6 reads.
5. **Activate the connection.** From here the system refuses the login
   proof when either object is absent or the connection is still a draft.
6. **After the first green login proof from `main`**, add the branch pin
   to the role: condition `ref` Equals `refs/heads/main`. Then prove the
   pin, since nothing else does: dispatch the probe from `main` and read
   `role <name>: granted`; dispatch it from any other branch and read
   `role <name>: not granted` (OPA still issues the connection's token
   there, since the role is only a hint when authenticating to the
   connection, and `sft resolve` then exits 125). A probe that says
   `granted` from the other branch means the pin does not hold
   (2026-10-08, F35: the first line alone said `accepted` from
   `develop` with the pin in place).

**What the names trust.** The claims match by name, so a person can read
every value off the remote URL. A fork's token names the fork and never
matches, and pull requests from forks get no token. A rename inside the
owner, followed by another repository taking the old name, makes the new
one match: treat a rename as a move. A deleted owner's name can be
registered again by someone else after GitHub's hold period; only an id
pin closes that (`repository_id` Equals `<repo-id>`,
`repository_owner_id` Equals `<owner-id>`), at the cost of a new
connection when the repository is recreated.

**When the repository moves** (a new repository, a new owner): make the
new connection as a draft with the new names, run the probe from the new
repository against it, activate it, bind or create the role, point
`workload_connection` / `workload_role` at the new names and run the
identity lifecycle, run the login proof from the new repository, and only
then deactivate the old connection, the same day.

### 3.6 The age identity CI opens the tree with

Every `ENC[age:...]` value in the tree is encrypted to the recipients in
`cfg/_config.yml`'s `encryption.recipients`. CI needs an identity of its
own among them:

```sh
age-keygen -o ci.agekey                       # prints the public key: age1...
# add that public key to encryption.recipients in cfg/_config.yml
CSIS_CONFIG_IDENTITY=<your own identity> cs-image-system --root-dir . reencrypt
gh secret set CSIS_CONFIG_IDENTITY -R <owner>/<repo> < ci.agekey
rm ci.agekey                                  # the secret store holds it now, and nothing else does
```

Commit the re-encrypted tree. The workflow writes the secret to a file on
the runner and masks every decrypted value in the log before anything
prints.

### 3.7 The secrets

| Secret | What reads it | Job | The value |
| --- | --- | --- | --- |
| `AWS_ROLE_ARN` | the AWS federation step, then the profile step | live, perform | the READ-ONLY role's ARN (section 3.3) |
| `AWS_APPLY_ROLE_ARN` | the AWS federation step before the performing run; held through the login proof | perform, when recording | the WRITE role's ARN (section 3.3) |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | the GCP auth steps | live, perform | the provider's full name (section 3.4) |
| `GCP_SERVICE_ACCOUNT` | the GCP auth steps | live, perform | the READ-ONLY service account's address (section 3.4) |
| `GCP_APPLY_SERVICE_ACCOUNT` | the GCP auth step before the performing run; held through the login proof | perform, when recording | the WRITE service account's address, or the read-only one (section 3.4, step 4) |
| `OKTA_API_PRIVATE_KEY` | the load's check that the `okta/okta` provider can authenticate | live, perform | the services app's private key, PEM (section 3.5) |
| `TF_VAR_KEY` | the load, exported as `TF_VAR_<team>_key` | live, perform | the OPA service user's API key |
| `TF_VAR_SECRET` | the load, exported as `TF_VAR_<team>_secret` | live, perform | the OPA service user's API secret |
| `CSIS_CONFIG_IDENTITY` | every load, to open `ENC[age:...]` values | live, perform | CI's age identity (section 3.6) |

A tree with one cloud has the gate lines for that cloud alone; the
starter for that cloud already leaves the other's secrets out.

One secret no gate reads: **`CSIS_PROOF_SSH_KEY`**, the private key of a
posix group's proof user (stage 75) -- a member declared
`is_service_account: true` on a posix user builder, with a `uid:` and its
public key in `public_keys:`. The perform job's login proof logs in as
that user over ssh, through the runtime's session tunnel (SSM on AWS, IAP
on GCE: no public address), and checks the group. A tree with no posix
proof user needs no such secret; a posix proof without it fails its first
check, naming the secret.

The login proof runs while the WRITE identity is still held, straight
after the performing step and before the read-only identity is taken back
(stage 89). The reason is the tunnel: opening a session to a machine is a
permission. On AWS it is `ssm:StartSession` (the "SessionManagerBake"
statement of section 3.3): the WRITE role has it because a bake travels
the same way, and the READ-ONLY role is not given it. On GCE it is the IAP
tunnel, which belongs with the roles a bake on GCE uses (section 3.4, step
4); a posix proof on GCE has not yet been made from CI. An Okta proof
needs nothing of the cloud but a read and is indifferent to which identity
is held.

Set each from a file or standard input, never as a command-line argument
(it would land in your shell history):

```sh
gh secret set AWS_ROLE_ARN -R <owner>/<repo>                 # prompts; paste, then Enter
gh secret set OKTA_API_PRIVATE_KEY -R <owner>/<repo> < okta-private-key.pem
gh secret list -R <owner>/<repo>                             # names only; values are never shown
```

**How the gate reads them.** GitHub gives a job no way to tell a missing
secret from an empty one, so each job decides on the set: none configured
is `SKIPPED`, said so in the job summary, and the job passes; some
configured and some missing (or empty) is `FAILED` with their names. A
secret created from an empty file exists and is empty: it fails the gate
by name, which is the point. None configured is tested first, so the
first push of a repository made with "Use this template", which goes to
`main` before any secret exists, is `SKIPPED` too; with some configured, a
push to `main` asks for a record, and the write identity's secret
(`AWS_APPLY_ROLE_ARN`, `GCP_APPLY_SERVICE_ACCOUNT`) is then required.

### 3.8 The proofs, in order

Each one green before the next; each is read in the job summary, because
a green job is not proof its steps ran. The summary is on the run's page
(`gh run view <run> --web`, or Actions in the browser), not in `gh run
watch` or `gh run view`, which print steps and annotations; a job that
was `SKIPPED` by its gate has no summary at all, and the gate's own line
(`live: SKIPPED -- no secret is configured ...`) is in the log of its
step "Gate on the secrets".

1. **`verify`** on a push to `develop`: the release installs, the
   `Justfile` parses, public-safe passes. Needs nothing but `.csis-version`.
2. **`live`** with the read-only secrets set: validate, config-drift, the
   strict state query and the modification tests all ran, not `SKIPPED`.
3. **The workload probe** dispatched against the draft connection (section
   3.5, step 4), then the connection activated.
4. **One `perform`**: `git push origin develop:main`, which creates
   `main` the first time (or Actions, CI, Run workflow on `main` with
   `mode: record`). The records land on `main`; bring them back with
   `git merge --ff-only origin/main` on `develop`. Before it, the
   identity and storage lifecycles should have applied once from your
   machine (the daily driver, 3.1 and 3.2): a `perform` plans the
   instance root, which reads those roots' state, and a storage root
   that never applied has none (the strict state query says so as a
   note).
5. **The login proof as a workload**: the "CI logs in through the managed
   policy" step green, and `meta-state/login-proofs.yaml` on `main` saying
   `as: workload`. Then the branch pin on the role, proved by the probe
   from two branches (section 3.5, step 6).

### 3.9 When it fails

| What you see | What it means | What to do |
| --- | --- | --- |
| `live: SKIPPED -- no secret is configured` and a green job | no secret exists yet; nothing ran | set the secrets (section 3.7) |
| `live: FAILED -- secrets are configured but these are missing or EMPTY: <names>` | some secrets exist, those do not (or are empty) | set the named ones; an empty one is re-set from a file that holds the value |
| `perform: FAILED -- recording was requested on main and these secrets are missing or EMPTY: <names>` on the FIRST push of a new repository, naming every secret | the workflow is from 0.1.2 or before, whose gate asked for the record before it saw that nothing was configured | nothing is wrong with the repository; the run proved nothing. Take a later release (section 3.1), or let the next run, with the secrets set, stand for it |
| `perform: FAILED -- recording was requested on main ...` naming only the write identity | a push to `main` records, and the record's write role (or GCP identity) is not set | set it (section 3.7); a run dispatched with `mode: dry` does not need it |
| `Failed to install entrypoints for cs-image-system` in "Install the released system" | `.csis-version` names a release before 0.1.1.dev2, whose whole-system package exposed no command to `uv tool install` | move `.csis-version` to a later release |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | the role's trust condition does not match the token's `sub` or `aud` | compare the trust policy with the subject form your organisation's tokens carry (section 3.2, step 4); CloudTrail's denied event shows the token's subject |
| `login proof <instance>: login: FAILED -- ssh <user>@<instance> id: exit 255` with `is not authorized to perform: ssm:StartSession` and the READ-ONLY role's name | the proof ran under the read-only role, which may not open a session: this tree's workflow is from a release before 0.1.1.dev22 (stage 89) | take the newer release (section 3.1): its workflow makes the proof while the write identity is held. Do not give the read-only role the session |
| the load says the AWS profile was not found, or no credentials | the profile step did not run, or the YAML names a different profile | read the "Name the federated credentials" step; it writes the profile the runtimes name |
| the probe exits 0 but issues no token | the connection is still a draft | activate it (section 3.5, step 5) |
| the probe's client refuses the token | a claim does not match | compare the claims the probe printed with the connection's Required Claims |
| `perform` fails at "Push the record" | `main` is protected against the job's own token, or someone pushed while the run was in flight | let `github-actions[bot]` push to `main` (section 3.2, step 3); never force |
| `runtime-unchanged: the emission of <runtime> CHANGED` | a declaration of `GUARD_RUNTIME` changed | apply that change by hand, from your own machine, then let `perform` run again |
| `runtime-unchanged: the emission of <runtime> CHANGED (1 files)`, the diff one `source_image` (or `image-id`) line, old and new, under `base-image/` | the system is 0.1.2 or before, and the vendor published a newer image under a base with no build yet: nothing of yours changed | nothing to apply: the record the job pushed already holds the move, so the next push to `main` passes the guard; a later release (section 3.1) passes it the first time |
| a state query storage `unavailable` | a read the READ-ONLY identity lacks | add the action CloudTrail (or GCP's audit log) names |

## 4. GitLab

Not written yet. What is known today: the release ships no
`.gitlab-ci.yml`; `cs-image-system workload token` reads GitHub's Actions
token endpoint alone; a GitLab pipeline would present its `id_tokens`
(issuer `https://gitlab.com` or your instance) to the same AWS, GCP and
OPA trusts, each of which accepts a different issuer and claim set.
Writing these sections is a later stage of the system, and so is the code
they need.

### 4.0 The bootstrap

TBD.

### 4.1 The pipeline this tree carries

TBD.

### 4.2 The project

TBD.

### 4.3 AWS

TBD.

### 4.4 GCP

TBD.

### 4.5 Okta and Okta Privileged Access

TBD.

### 4.6 The age identity CI opens the tree with

TBD.

### 4.7 The CI/CD variables

TBD.

### 4.8 The proofs, in order

TBD.

### 4.9 When it fails

TBD.
