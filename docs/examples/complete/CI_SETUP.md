# Setting up CI for a configuration repository, from scratch

This guide takes a configuration repository written by `cs-image-system
init-config` (or copied from a starter tree) from "it validates on my
machine" to "its CI proves it, records it and performs on `main`". It is
the same text in every starter tree and in the release; the system's
tests hold its secrets table to the workflow the release ships, so the
names below are the names the workflow reads.

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
   --extra-index-url https://pypi.org/simple/`).
2. `just init`: the public-safe hook, the plugin cache, a check that the
   command runs, and a line saying which command a run's callbacks will
   find. A run's own steps and the runner scripts call the command back
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

```sh
cd generated/bootstrap && tofu init && tofu plan && tofu apply && cd ../..
bash generated/bootstrap/set-secrets.sh      # one file per secret under _uncommitted/secrets (or SECRETS_DIR)
```

What the sections do today, and what stays by hand:

| Section | Terraform does | By hand, still |
| --- | --- | --- |
| GitHub (3.2, 3.7) | the default branch; a ruleset on the production branch (no deletion, no force push) that the GitHub Actions app bypasses, so `perform` still pushes its records; Actions enabled with read-only workflow permissions; the Actions variables `PERFORM_RUNTIME`, `GUARD_RUNTIME`, `AWS_REGION` | the secret VALUES (one file each, then the script); the `REPLACE-ME` literals in `ci.yml`, until a release makes the workflow read `vars` |
| AWS (3.3) | the GitHub OIDC identity provider (read when it exists); the READ-ONLY and WRITE roles with the trust and permission documents of 3.3, the subject forms you chose, your bucket, prefix, region, account and instance profile filled in (a role that exists is ADOPTED by an `import` block, so its trust is maintained from then on, and every subject it already trusted that is not this repository's -- another repository sharing the role -- is KEPT unless you drop it at the prompt); the state bucket and the Session Manager instance profile only when the account lacks them; `AWS_ROLE_ARN` and `AWS_APPLY_ROLE_ARN` set by the script from the applied root's outputs | the network, which is yours and never modified; removing a hand-made inline policy from an adopted role once the plan is clean |
| GCP (3.4) | the workload identity pool and its GitHub provider (the mapping of 3.4 and a condition admitting this repository alone); the READ-ONLY service account with its project roles, and the WRITE one when CI performs on a GCE runtime; the `workloadIdentityUser` bindings (the write one on the production branch alone); the three GCP secrets set by the script from the applied root's outputs. What already exists is READ, never rewritten, and every role and binding is one member added | the network and firewall, which are yours; adding this repository to an EXISTING provider's condition when it does not name it (the README of the generated root says when) |
| Okta and OPA (3.5) | a later iteration decides what the providers can make | everything in 3.5 today; the workload connection and role are by hand in any case |
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

The root's state follows the bucket. When the state bucket exists, the
root is bound to the tree's declared S3 backend at
`<state prefix>/bootstrap.tfstate`, like every other root. When the
bootstrap is what makes the bucket, the first apply keeps its state in
`terraform.tfstate` beside the root (never committed); then run `just
bootstrap` again -- the bucket now exists, so the root binds to it -- and
`tofu init -migrate-state` in `generated/bootstrap`.

### 3.1 The workflows this tree carries

`.github/workflows/ci.yml` has three jobs:

| Job | When | What it does | Holds |
| --- | --- | --- | --- |
| `verify` | every push and pull request | installs the release, parses the `Justfile`, runs `just public-safe` | no secret |
| `live` | pushes and the nightly schedule, never pull requests | validate, is the committed emission current, the strict state query, the modification tests under docker | the READ-ONLY identities |
| `perform` | `main` (or a dispatch asking to record) | the record, the guard on `GUARD_RUNTIME`, the performing run of `PERFORM_RUNTIME` under the WRITE identity, the login proof as a workload, the closing record, the strict state query | the read-only identities, and the write identity for one step |

`.github/workflows/opa-workload-probe.yml` is dispatch only: it presents
this repository's OIDC token to your OPA workload connection and stops
(section 3.5).

Replace every `REPLACE-ME` in `ci.yml` before the first push that should
run `live`:

| Value | Meaning |
| --- | --- |
| `PERFORM_RUNTIME` | the runtime the `perform` job bakes, releases and applies retention on (a `name:` from `cfg/runtime-builders.yml`) |
| `GUARD_RUNTIME` | a runtime CI must never bake on (for example one billed to a person), or empty for none; its emission may not change between two records, or `perform` fails before anything performs |
| `AWS_REGION` | the region of the AWS runtime (absent in a GCE-only tree) |
| `TF_VAR_REPLACE_ME_key`, `TF_VAR_REPLACE_ME_secret` | rename to `TF_VAR_<team>_key` and `TF_VAR_<team>_secret`, where `<team>` is the OPA team with every non-alphanumeric character as `_` (the `team:` on your group builder); the values come from the `TF_VAR_KEY` and `TF_VAR_SECRET` secrets, which keep those names |

`.csis-version` pins the release CI installs. Taking a new release is:
move the version in that file, run `cs-image-system init-config . --force`
with the new release to refresh the release-owned parts, review the diff,
commit.

### 3.2 The repository

1. **Branches.** `develop` is the default branch and where people push;
   `main` is what `perform` runs on. Merge `develop` into `main` to
   perform; the records `perform` writes are pushed back to `main`.
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
   ```

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
`iam_instance_profile`). The lifecycles generate no IAM. These roles are
made once: either by the bootstrap (3.0), which writes exactly these
documents as terraform you apply, or by a person in the console as
described here.

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
   Filestore. Let the repository impersonate it:

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
   names. Against a draft, OPA validates the token and issues nothing
   usable; the log shows the token's claims and the client's verdict.
   Green here is the proof the claims match.
5. **Activate the connection.** From here the system refuses the login
   proof when either object is absent or the connection is still a draft.
6. **After the first green login proof from `main`**, add the branch pin
   to the role: condition `ref` Equals `refs/heads/main`.

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
| `AWS_APPLY_ROLE_ARN` | the AWS federation step before the performing run | perform, when recording | the WRITE role's ARN (section 3.3) |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | the GCP auth steps | live, perform | the provider's full name (section 3.4) |
| `GCP_SERVICE_ACCOUNT` | the GCP auth steps | live, perform | the READ-ONLY service account's address (section 3.4) |
| `GCP_APPLY_SERVICE_ACCOUNT` | the GCP auth step before the performing run | perform, when recording | the WRITE service account's address, or the read-only one (section 3.4, step 4) |
| `OKTA_API_PRIVATE_KEY` | the load's check that the `okta/okta` provider can authenticate | live, perform | the services app's private key, PEM (section 3.5) |
| `TF_VAR_KEY` | the load, exported as `TF_VAR_<team>_key` | live, perform | the OPA service user's API key |
| `TF_VAR_SECRET` | the load, exported as `TF_VAR_<team>_secret` | live, perform | the OPA service user's API secret |
| `CSIS_CONFIG_IDENTITY` | every load, to open `ENC[age:...]` values | live, perform | CI's age identity (section 3.6) |

A tree with one cloud has the gate lines for that cloud alone; the
starter for that cloud already leaves the other's secrets out.

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
by name, which is the point.

### 3.8 The proofs, in order

Each one green before the next; each is read in the job summary, because
a green job is not proof its steps ran.

1. **`verify`** on a push to `develop`: the release installs, the
   `Justfile` parses, public-safe passes. Needs nothing but `.csis-version`.
2. **`live`** with the read-only secrets set: validate, config-drift, the
   strict state query and the modification tests all ran, not `SKIPPED`.
3. **The workload probe** dispatched against the draft connection (section
   3.5, step 4), then the connection activated.
4. **One `perform`**: merge `develop` into `main` (or Actions, CI, Run
   workflow on `main` with `mode: record`). The records land on `main`.
5. **The login proof as a workload**: the "CI logs in through the managed
   policy" step green, and `meta-state/login-proofs.yaml` on `main` saying
   `as: workload`. Then the branch pin on the role (section 3.5, step 6).

### 3.9 When it fails

| What you see | What it means | What to do |
| --- | --- | --- |
| `live: SKIPPED -- no secret is configured` and a green job | no secret exists yet; nothing ran | set the secrets (section 3.7) |
| `live: FAILED -- secrets are configured but these are missing or EMPTY: <names>` | some secrets exist, those do not (or are empty) | set the named ones; an empty one is re-set from a file that holds the value |
| `Failed to install entrypoints for cs-image-system` in "Install the released system" | `.csis-version` names a release before 0.1.1.dev2, whose whole-system package exposed no command to `uv tool install` | move `.csis-version` to a later release |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | the role's trust condition does not match the token's `sub` or `aud` | compare the trust policy with the subject form your organisation's tokens carry (section 3.2, step 4); CloudTrail's denied event shows the token's subject |
| the load says the AWS profile was not found, or no credentials | the profile step did not run, or the YAML names a different profile | read the "Name the federated credentials" step; it writes the profile the runtimes name |
| the probe exits 0 but issues no token | the connection is still a draft | activate it (section 3.5, step 5) |
| the probe's client refuses the token | a claim does not match | compare the claims the probe printed with the connection's Required Claims |
| `perform` fails at "Push the record" | `main` is protected against the job's own token, or someone pushed while the run was in flight | let `github-actions[bot]` push to `main` (section 3.2, step 3); never force |
| `runtime-unchanged: the emission of <runtime> CHANGED` | a declaration of `GUARD_RUNTIME` changed | apply that change by hand, from your own machine, then let `perform` run again |
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
