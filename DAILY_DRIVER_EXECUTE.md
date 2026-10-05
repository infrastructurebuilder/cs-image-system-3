# Executing the daily driver walk (stage 65)

*How the walk of [DAILY_DRIVER.md](DAILY_DRIVER.md) is run: on a Fedora 43
container, as one user, in stages. The daily driver stays the text being
tested. This page is the scaffolding around it: the machine, the
credentials, and for each stage what to read, what to type, and what to
tell Claude afterwards. Where the daily driver turned out to say too
little, this page gives the missing command and marks it as a finding.*

## How the stages work

1. Do ONE stage, typing the commands as `mykel.alvis` in the container.
2. Tell Claude `stage N done`, or paste the error you hit.
3. Claude reads what you ran and what it left (below), confirms the
   stage or explains the failure, logs any finding, and names the next
   stage.

**What Claude can see.** Every command you type in an interactive shell
is appended to `~/.bash_history` in the container as it runs, with its
time. Claude reads that file and the repository on the mounted volume
(`generated/`, `meta-state/`, the git log). Claude does NOT see command
output, so paste any error or surprising output into the chat. Claude
is not watching between your messages; it looks when you write.

**Secrets.** Three rules:

- Never paste a secret value into the chat.
- Secret values go in two files only: `~/.aws/credentials` (stage 3) and
  the repository's gitignored `.envrc` (stage 5). Claude does not open
  either file.
- A command typed with a LEADING SPACE is not recorded in the history.
  Use it for anything that carries a secret on the command line.

## The machine (made by Claude; nothing for you to do)

| What | Value |
| --- | --- |
| Container | `csis-walk`, image `csis-walk:fedora43` (Fedora 43, `dnf -y update` applied at build) |
| User | `mykel.alvis` (uid 1000), `sudo` without a password, an otherwise untouched home |
| Preinstalled | nothing the daily driver asks for: no `git`, no `just`, no `cs-image-system` |
| The volume | host `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-walk` is `/walk/cs-image-system-walk` in the container |
| Lifetime | runs until removed; survives `docker stop`/`start` and a restart of OrbStack |
| Definition | `_uncommitted/walk-container/` (`Dockerfile`, `run.sh`); `run.sh` rebuilds it from nothing, which discards the home directory and every installed tool |

The home directory lives in the container, not on the volume: tools,
`~/.aws`, the age identity and the installed release are lost if the
container is removed. The repository is on the volume and is not.

The container cannot reach the host's Docker. `just test-mods` (the
modification tests) needs Docker, so that step is a decision when the
walk reaches it.

## Stage 1 -- enter the container

From any terminal on the Mac:

```sh
docker exec -it -u mykel.alvis -w /walk/cs-image-system-walk csis-walk bash -l
```

Then, inside:

```sh
whoami && cat /etc/fedora-release && pwd && ls -la
sudo -n true && echo "sudo works"
```

Expected: `mykel.alvis`, `Fedora release 43`, `/walk/cs-image-system-walk`,
your `README.md` and `.git`. Use the same `docker exec` line every time
you come back; each one is a fresh login shell.

**Report:** `stage 1 done`.

## Stage 2 -- the tools (DAILY_DRIVER 1.2)

Read section 1.2's table first: it says WHAT is needed and the floors.
It does not say how to install anything (finding F5). These commands
were proved on this image on 2026-10-05; everything Fedora carries
comes from Fedora, and four tools come from their vendors.

```sh
# from Fedora's own repositories
sudo dnf -y install git jq yq age gh ansible-core awscli2 just uv opentofu \
  unzip which openssh-clients dnf5-plugins less vim-minimal

# Packer (HashiCorp's repository)
sudo dnf config-manager addrepo --from-repofile=https://rpm.releases.hashicorp.com/fedora/hashicorp.repo
sudo dnf -y install packer

# the Google Cloud CLI (Google's repository)
sudo tee /etc/yum.repos.d/google-cloud-sdk.repo >/dev/null <<'R'
[google-cloud-cli]
name=Google Cloud CLI
baseurl=https://packages.cloud.google.com/yum/repos/cloud-sdk-el10-x86_64
enabled=1
gpgcheck=1
repo_gpgcheck=0
gpgkey=https://packages.cloud.google.com/yum/doc/rpm-package-key-v10.gpg
R
sudo dnf -y install google-cloud-cli

# sft, the Okta Privileged Access client (Okta's repository; the RHEL 10 path works on Fedora 43)
sudo rpm --import https://dist.scaleft.com/GPG-KEY-OktaPAM-2023
sudo tee /etc/yum.repos.d/oktapam-stable.repo >/dev/null <<'R'
[oktapam-stable]
name=Okta PAM Stable
baseurl=https://dist.scaleft.com/repos/rpm/stable/rhel/10/x86_64
gpgcheck=1
repo_gpgcheck=1
enabled=1
gpgkey=https://dist.scaleft.com/GPG-KEY-OktaPAM-2023
R
sudo dnf -y install scaleft-client-tools

# the Session Manager plugin (AWS's rpm)
sudo dnf -y install https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_64bit/session-manager-plugin.rpm
```

Check them against the table:

```sh
just --version; git --version; uv --version; tofu --version | head -1; packer --version
aws --version; gcloud --version | head -1; ansible-playbook --version | head -1
bash --version | head -1; yq --version; jq --version; sft --version
session-manager-plugin --version; age --version; gh --version | head -1
```

Expected, at least: just 1.57, tofu 1.11, packer 1.16, aws-cli 2.37,
gcloud 587, ansible-core 2.18, bash 5, yq 4.53, jq 1.8, sft 1.115.
Docker is absent on purpose (see "The machine").

**Report:** `stage 2 done`, or the first command that failed and its
last lines.

## Stage 3 -- AWS access keys

You are supplying short-lived access keys, not logging in.

**Why a file and not only environment variables.** The configuration
names a profile (`credentials.profile_name` on the runtime, `profile`
on the state backend), and when a profile is named the AWS SDK ignores
`AWS_ACCESS_KEY_ID` and friends in the environment. So the keys go in
the credentials file UNDER THAT PROFILE'S NAME. The walk uses the
profile name `noaa`, as the reference configuration does.

1. In a browser on the Mac: the AWS access portal, the account, the
   role, "Access keys". Copy the three values (access key id, secret
   access key, session token).
2. In the container (the editor is `vi`; nothing here goes in the
   history):

   ```sh
   mkdir -p ~/.aws && chmod 700 ~/.aws
   printf '[profile noaa]\nregion = us-east-2\noutput = json\n' > ~/.aws/config
   vi ~/.aws/credentials
   ```

   and make the file exactly this, with your three values:

   ```ini
   [noaa]
   aws_access_key_id = ...
   aws_secret_access_key = ...
   aws_session_token = ...
   ```

   ```sh
   chmod 600 ~/.aws/credentials
   export AWS_PROFILE=noaa AWS_REGION=us-east-2
   aws sts get-caller-identity
   ```

Expected: your account `514190660293` and the role's ARN.

**When the keys expire** (`ExpiredToken`, or `The security token
included in the request is expired`): copy fresh keys from the portal
and replace the three lines in `~/.aws/credentials`. Nothing else
changes. A long run (a bake) needs keys that outlive it, so refresh
them before starting one.

**Report:** `stage 3 done` (do not paste the identity output's ARN if
you would rather not; "it printed my identity" is enough).

## Stage 4 -- the release (DAILY_DRIVER 1.1)

Read section 1.1. Its command, `uv tool install cs-image-system`,
fails today: no release is on PyPI, every one is a development version
on TestPyPI (finding F1). The form that works is the CI guide's:

```sh
uv tool install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ "cs-image-system==0.1.1.dev14"
export PATH="$HOME/.local/bin:$PATH"     # only if `cs-image-system` is not found
cs-image-system --help | head -5
```

If `uv` warns that `~/.local/bin` is not on `PATH`, run `uv tool
update-shell`, leave the container and enter it again.

**Report:** `stage 4 done`, and say whether you needed the `PATH`
line.

## Stage 5 -- the repository, from the starter (DAILY_DRIVER 1.9, 1.6, 1.7)

Read section 1.9 through its step 2. Your clone already exists, and
that matters: `init-config` writes the whole starter only into a
directory with nothing in it, and a clone always has `.git`, so run in
the clone it writes the release's files and NO configuration (finding
F6). The way round: write the starter somewhere empty and copy it in.

```sh
cd /walk/cs-image-system-walk
git config --global user.name "Mykel Alvis"
git config --global user.email "104666+mykelalvis@users.noreply.github.com"
git checkout develop                      # CI_SETUP 3.2: develop is where people push, main is what perform runs on
cs-image-system init-config /tmp/starter --from standard-aws      # expect: "the whole tree ... 75 written"
cp -a /tmp/starter/. . && rm -rf /tmp/starter                     # your README.md is replaced by the starter's
git status --short | head
just init
```

The first commit is refused as the tree stands (finding F4: the
public-safe hook flags the copyright holder's address in the header of
every file the release wrote). Allow it by decision, as the refusal
says. Open `cfg/_config.yml`, find `public_safe:` / `allow:`, and add
one line under the `path:.age-identity` line:

```yaml
    - "mykelalvis@infrastructurebuilder.org"   # the copyright holder in the SPDX header of every release-owned file: public by intent
```

```sh
git add -A && git commit -m "The standard-aws starter, as init-config wrote it (cs-image-system 0.1.1.dev14)"
```

**The age identity** (1.9 step 2; the page does not say how to make
one, finding F2):

```sh
mkdir -p ~/.config/cs-image-system/age && chmod 700 ~/.config/cs-image-system/age
age-keygen -o ~/.config/cs-image-system/age/walk.age-identity
```

It prints `Public key: age1...`. In `cfg/_config.yml`, under
`encryption:` / `recipients:`, replace the test recipient with that
public key. Then rotate every encrypted value to it, opening them with
the TEST identity one last time, and drop the test identity:

```sh
CSIS_CONFIG_IDENTITY=.age-identity just cli reencrypt
git rm -q .age-identity
```

and delete the `path:.age-identity` line from `public_safe.allow`.
(`.age-recipient`, if the starter wrote one, holds the test public key:
delete it too if nothing else names it. Tell Claude what you find.)

**The shell file** (1.7): create `.envrc` in the repository. It is
gitignored. For now it needs one line; stage 7 adds the Okta and OPA
values.

```sh
printf 'export CSIS_CONFIG_IDENTITY=$HOME/.config/cs-image-system/age/walk.age-identity\n' > .envrc
source .envrc
```

**Report:** `stage 5 done`, plus anything the pages did not prepare
you for.

## Stage 6 -- the values, then validate and dry (DAILY_DRIVER 1.9 steps 3-4, section 2)

**6a. Finish stage 5's leftovers.** Three things the pages do not
mention (finding F7):

```sh
cd /walk/cs-image-system-walk && source .envrc
git rm -q .age-recipient         # the TEST public key; nothing reads it once the test identity is gone
```

In `cfg/_config.yml`, the comment above `encryption:` still says the
recipient is the TEST one, and the line itself ends `# REPLACE: ...`.
Reword both to say it is the walk's own key. Then commit:

```sh
git add -A && git commit -m "The walk's own age identity; the test identity removed"
```

**6b. The plain values.** Every `REPLACE-ME` becomes a real value
(`grep -rn REPLACE-ME cfg groups` lists them; ignore the workflows
until stage 8).

| File | Field | Value |
| --- | --- | --- |
| `cfg/_config.yml` | `id` | `cs-image-system-walk` |
| | `okta_gateway_selector` | `environment=staging` |
| | `admin_public_keys` | the public key of a pair made for the walk (below) |
| `cfg/runtime-builders.yml` | `profile_name` | `noaa` |
| | `session_instance_profile` | `AmazonSSMRoleForInstancesQuickSetup` |
| | `tags.Project` | `cs-image-system-walk` |
| | `network` | `vpc-0c78d0d63b7a100df` |
| | both security group lists | `sg-03015ec107ae5f81a` (the Okta gateway's) |
| | `subnet_id` | `subnet-09f79018af845358a` (us-east-2a, private) |
| `cfg/storage-builders.yml` | `tags.Project` | `cs-image-system-walk` |
| `cfg/state-backends.yml` | `bucket` | `csis-walk-tfstate-514190660293` (it does not exist yet: the bootstrap creates it at stage 9) |
| | `key` | `statefiles/cs-image-system-walk/` |
| | `profile` | `noaa` |
| `cfg/group-builders.yml` | `org` (twice) | `noaa` |
| | `team` (twice) | `nos-coastal-modeling-cloud-sandbox` |

The admin key pair (no passphrase; the private half stays in the
container's home):

```sh
ssh-keygen -t ed25519 -f ~/.ssh/walk_admin -N '' -C csis-walk-admin
cat ~/.ssh/walk_admin.pub        # this whole line replaces the placeholder key in admin_public_keys
```

Check each subnet/zone line beside the ones you replaced: the starter's
`availability_zone` must say `us-east-2a` for that subnet.

**6c. The names that are the walk's.** Nothing here may collide with
the reference configuration in the same account and OPA team.

| File | Change |
| --- | --- |
| `groups/groups.yaml` | the group's `name`: `team` becomes `walk_team` |
| `images/images.yaml` | `group: team` becomes `group: walk_team` |
| `storages/storages.yaml` | under `groups:`, `team` becomes `walk_team` |
| `instances/instances.yaml` | the instance's `name`: `team-node-1` becomes `walk-node-1` (it is the hostname OPA will know) |

**6d. The one person: you.** The roster's two personas are replaced by
your Okta account. Each identifying value is committed encrypted; the
commands start with a SPACE so the values stay out of the history.

```sh
 just cli encrypt 'YOUR-OPA-USERNAME'       # prints one ENC[age:...] marker
 just cli encrypt 'YOUR-ORG-MAIL-DOMAIN'    # the part after @ in your Okta login
```

- `groups/users.yaml`: delete both personas; write one user whose
  `name:` is the first marker, with your `first_name` and `last_name`.
  Fix the comment that names the personas.
- `groups/groups.yaml`: delete the `members:` block; under `admins:`
  put the SAME first marker (run `encrypt` once and paste it twice: two
  runs give two different markers, and that is fine too).
- `cfg/group-builders.yml`: `email_domain:` takes the second marker in
  place of `example.invalid`.

**6e. Validate and dry.** Leave every `apply_*` flag `false`.

```sh
source .envrc && export AWS_PROFILE=noaa AWS_REGION=us-east-2
just preflight
just validate
```

`validate` is expected to stop on the OPA credentials (the daily driver,
1.5: they are needed at load, not only at apply). If that is the only
complaint, stage 6 is done; `just dry` and the commit come at the end
of stage 7. Any OTHER complaint is a value to fix here.

**Report:** `stage 6 done` and what `validate` said (paste it; it
carries no secret).

## Stage 7 -- Okta and OPA in the shell (DAILY_DRIVER 1.5, 1.7)

Add to `.envrc`, with the editor, the names section 1.5's table lists.
The values are the reference configuration's; copy them by hand from
its `.envrc` on the Mac, never through the chat:

```sh
export OKTA_API_CLIENT_ID=...
export OKTA_API_PRIVATE_KEY_ID=...
export OKTA_API_SCOPES=...
export OKTA_API_PRIVATE_KEY=...        # the PEM itself, or the path of a copy inside the container
export OKTA_RESOURCE_GROUP=...
export TF_VAR_nos_coastal_modeling_cloud_sandbox_key=...
export TF_VAR_nos_coastal_modeling_cloud_sandbox_secret=...
```

Then `source .envrc`, `just validate`, `just dry`, and commit
`generated/` and `meta-state/` with the tree.

The `sft` client's own enrollment (`sft enroll`, `sft login`) wants a
browser. Whether it offers a URL to open on the Mac from inside a
container is something this stage finds out; it is needed only for the
login proof by hand, much later.

**Report:** `stage 7 done`.

## Stage 8 onward -- written when you reach them

These stages depend on what the earlier ones produce (the bootstrap's
interview, the names it prints), so their exact commands are added to
this page as each one comes up. The order, and the page each follows:

| Stage | What | Follows |
| --- | --- | --- |
| 8 | GitHub from the container: a token, `gh`, pushing `develop` and `main`; the workflow's `REPLACE-ME` values | CI_SETUP 3.1, 3.2 |
| 9 | `just bootstrap`: the interview, the apply that CREATES the walk's two roles and its state bucket, the state migration, the secrets script | DAILY_DRIVER 1.8; CI_SETUP 3.0, 3.3, 3.7 |
| 10 | The OPA workload connection and role, in the console, from what the bootstrap prints | CI_SETUP 3.5 |
| 11 | CI green: `verify`, `live`, the probe, one `perform` | CI_SETUP 3.8 |
| 12 | Making things: identity, storage, a base image, an instance image, the durable machine, the group on it, the login proof | DAILY_DRIVER 3 |
| 13 | Changing things: a modification re-baked; a membership | DAILY_DRIVER 4 |
| 14 | The failure walk | DAILY_DRIVER 6 |
| 15 | The GCE leg, one cycle (credentials below) | DAILY_DRIVER 1.4; CONFIGURATION |
| 16 | The second walk, `standard-aws-posix`, in its own repository (needs a second mounted volume: Claude re-creates the container from a snapshot of this one) | DAILY_DRIVER 1.9, 3.1 |
| 17 | Teardown and its proof | stage 65, step 8 |

## Google Cloud credentials through the environment

AWS has a pair of keys you can export. Google Cloud does not: its
credentials are either a FILE or a short-lived TOKEN, and the
environment only points at them. Three ways, from closest-to-AWS to
most useful here:

**1. An access token in the environment (lasts one hour).** The nearest
thing to AWS session keys. On a machine where you are logged in:

```sh
gcloud auth print-access-token                      # as yourself
gcloud auth print-access-token --impersonate-service-account=<runner>@<project>.iam.gserviceaccount.com
```

and in the container (with a leading space, so the history skips it):

```sh
 export CLOUDSDK_AUTH_ACCESS_TOKEN=<token>     # the gcloud CLI itself
 export GOOGLE_OAUTH_ACCESS_TOKEN=<token>      # OpenTofu's google provider, and Packer's googlecompute builder
export GOOGLE_CLOUD_PROJECT=<project> CLOUDSDK_CORE_PROJECT=<project>
```

Its limit: Google's Python client libraries, which this system's GCE
runtime uses for its state query, do not read a token from the
environment. They want Application Default Credentials, which is a
file. So a token alone does not carry a whole run of this system.

**2. A credentials file, named by the environment.** This is what the
system's own CI does.

```sh
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/gcp-credentials.json            # every library, tofu, packer
export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE=$HOME/gcp-credentials.json    # the gcloud CLI
export GOOGLE_CLOUD_PROJECT=<project> CLOUDSDK_CORE_PROJECT=<project>
```

The file is one of two things:

- **A copy of your Mac's Application Default Credentials**
  (`~/.config/gcloud/application_default_credentials.json`, the file
  `gcloud auth application-default login --impersonate-service-account=...`
  wrote). It holds your refresh token and the impersonation of the
  runner service account, so it keeps working until you revoke it.
  Nothing new is created in the project.
- **A service-account key** (`gcloud iam service-accounts keys create
  key.json --iam-account=<runner>@<project>.iam.gserviceaccount.com`).
  The true equivalent of a long-lived AWS access key: it never expires
  until deleted, an organisation policy may forbid creating one, and it
  must be deleted when the walk ends.

**3. Logging in inside the container** (`gcloud auth login
--no-launch-browser`, which prints a URL to open on the Mac). Not what
you asked for, listed for completeness.

**For the walk's GCE leg (stage 15)** the recommendation is way 2 with
a copy of your Mac's ADC file: it is the same identity your Mac already
uses, it creates nothing, and it serves every tool. You place the file
in the container's home yourself; it never goes on the volume and
Claude does not open it. IAP sessions additionally need an SSH key in
the container without a passphrase; that is set up at stage 15.

## Findings so far

Carried in the walk log (`_uncommitted/walk-log.md`); each is fixed in
the daily driver's words at the end of the stage, or filed as code.

| | Finding | Kind |
| --- | --- | --- |
| F1 | 1.1's install command cannot install any release that exists (TestPyPI only) | words |
| F2 | "Generate your own age key pair" does not say how; `age` is not in 1.2's tool table | words |
| F3 | 1.9 says `git init`; a fresh machine then has `master`, while the guide expects `develop` and `main` | words |
| F4 | the starter's own public-safe hook refuses the first commit of the tree `init-config` wrote | code |
| F5 | 1.2 lists the tools and floors, not how to install any of them | words |
| F6 | `init-config` in a cloned repository writes no configuration: only a directory with no entries counts as new, and a clone has `.git` | code |
| F7 | after the identity is replaced, `.age-recipient` and the comments that call the recipient the TEST one are left behind; no page says to tidy them | words |
