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

**Two places.** Every command in this page runs in one of two places,
and each step says which. *The container* is `csis-walk`: every stage
runs there unless it says otherwise. *Your local machine* is the host
the container runs on, whatever its operating system: your own
terminal, your browser, your other checkouts. A step for your local
machine says so in its first words, and says that it is NOT the
container.

**Watching CI.** After a `git push` or a `gh workflow run`, GitHub
takes a moment to start the run, so every `gh run watch` in this page
is preceded by `sleep 2`. If it still says no run is in progress,
the run may already be over: `gh run list --limit 3`.

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
| `direnv` | installed and hooked for every interactive shell, `root` and `mykel.alvis` (your request, finding F9); the repository's `.envrc` is allowed for both |
| The volume | the directory `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-walk` on your local machine (this walk's path) is `/walk/cs-image-system-walk` in the container |
| Lifetime | runs until removed; survives `docker stop`/`start` and a restart of the Docker runtime on your local machine |
| Definition | `_uncommitted/walk-container/` (`Dockerfile`, `run.sh`); `run.sh` rebuilds it from nothing, which discards the home directory and every installed tool |

The home directory lives in the container, not on the volume: tools,
`~/.aws`, the age identity and the installed release are lost if the
container is removed. The repository is on the volume and is not.

**direnv.** Entering the repository's directory loads `.envrc` by
itself; the `source .envrc` lines in the stages below are then
harmless and unnecessary. After EVERY edit of `.envrc`, run `direnv
allow` in the repository, or direnv refuses to load it and says so.
A shell that was open before direnv was installed needs to be left
and entered again. The non-secret lines `export AWS_PROFILE=noaa` and
`export AWS_REGION=us-east-2` can live in `.envrc` too. As `root` the
file loads as well, but its `$HOME` paths then point at root's home,
where there is no age identity: run the walk as `mykel.alvis`.

The container cannot reach the host's Docker. `just test-mods` (the
modification tests) needs Docker, so that step is a decision when the
walk reaches it.

## Stage 1 -- enter the container

From any terminal on your local machine (the host, not the
container):

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

1. In a browser on your local machine: the AWS access portal, the
   account, the role, "Access keys". Copy the three values (access
   key id, secret access key, session token).
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

**7a. Two things left from stage 6** (Claude's check of the tree):

- `storages/storages.yaml`, under `groups:`, still says `team`; make it
  `walk_team` (validation would refuse a storage that allows a group
  that does not exist).
- `.age-recipient` is still there and nothing is committed since the
  starter: `git rm -q --cached .age-recipient; rm .age-recipient`.
  The commit comes at the end of this stage.

**7b. The credentials.** Add to `.envrc`, with the editor, the names section 1.5's table lists.
The values are the reference configuration's; copy them by hand from
its `.envrc` on your local machine, never through the chat:

```sh
export OKTA_API_CLIENT_ID=...
export OKTA_API_PRIVATE_KEY_ID=...
export OKTA_API_SCOPES=...
export OKTA_API_PRIVATE_KEY=...        # the PEM itself, or the path of a copy inside the container
export OKTA_RESOURCE_GROUP=...
export TF_VAR_nos_coastal_modeling_cloud_sandbox_key=...
export TF_VAR_nos_coastal_modeling_cloud_sandbox_secret=...
```

Then:

```sh
direnv allow                 # .envrc changed; without this direnv refuses to load it
just validate
just dry
git add -A && git commit -m "The walk's values, its one person, and the first dry run"
```

`just validate` should end `Validation successful.` Read what `just
dry` wrote, as section 2 says, before committing; `generated/` and
`meta-state/` are part of the commit.

The `sft` client's own enrollment (`sft enroll`, `sft login`) wants a
browser. Whether it offers a URL to open in a browser on your local
machine, from inside a container, is something this stage finds out;
it is needed only for the login proof by hand, much later.

**Report:** `stage 7 done`.

## Stage 8 -- GitHub from the container (CI_SETUP 3.1, 3.2)

Read CI_SETUP.md sections 3.1 and 3.2 in the tree first.

**8a. Finish stage 7** if you have not: remove `.age-recipient` and
commit (the two lines at the end of stage 7).

**8b. A token.** The container has no browser and no SSH key, so `git`
and `gh` use a token. On github.com: Settings, Developer settings,
Fine-grained tokens, Generate new token.

- Resource owner `infrastructurebuilder`; repository access: only
  `cs-image-system-walk`.
- Repository permissions, each derived from what the walk's commands
  touch (no page lists them: finding F12):

  | Permission | Access | Why |
  | --- | --- | --- |
  | Metadata | read | every API call; GitHub adds it by itself |
  | Contents | read and write | `git push` |
  | Workflows | read and write | pushing `.github/workflows/` |
  | Administration | read and write | the bootstrap's default branch, Actions permissions and ruleset on `main` |
  | Variables | read and write | the bootstrap's Actions variables |
  | Secrets | read and write | `set-secrets.sh` |
  | Actions | read and write | `gh run watch`; starting the dispatch-only OPA probe (stage 10) |

  If the bootstrap's apply (stage 9) answers 403, the error names the
  call; add the permission it lacks and tell Claude.
- Expiry: a week covers the walk.

Add two lines to `.envrc` with the editor, then allow it:

```sh
export GH_TOKEN=github_pat_...          # gh reads this
export GITHUB_TOKEN=$GH_TOKEN           # the bootstrap's terraform reads this
```

```sh
direnv allow
gh auth status                           # "Logged in to github.com ... (GH_TOKEN)"
gh auth setup-git                        # git over https uses the token
git config --global url."https://github.com/".insteadOf "git@github.com:"   # your clone's remote is ssh; this rewrites it in the container only
git ls-remote origin | head -3           # proves git can reach the repository
```

**8c. The ids** (CI_SETUP 3.2 step 4; keep the output for stage 9):

```sh
gh api repos/infrastructurebuilder/cs-image-system-walk --jq .id
gh api users/infrastructurebuilder --jq .id
gh api repos/infrastructurebuilder/cs-image-system-walk/actions/oidc/customization/sub
```

(The guide's third command asks the ORGANISATION, which a token scoped
to one repository may not read: 403, finding F13. The repository form
above answers with the permissions you have.)

**8d. The workflow's values.** In `.github/workflows/ci.yml`:

| Line | Value |
| --- | --- |
| `PERFORM_RUNTIME` | `aws-main` (the starter's one runtime; check its `name:` in `cfg/runtime-builders.yml`) |
| `GUARD_RUNTIME` | `""` (leave empty until the GCE leg, stage 15) |
| `AWS_REGION` | `us-east-2` |
| `TF_VAR_REPLACE_ME_key` (twice) | `TF_VAR_nos_coastal_modeling_cloud_sandbox_key` |
| `TF_VAR_REPLACE_ME_secret` (twice) | `TF_VAR_nos_coastal_modeling_cloud_sandbox_secret` |

Only the variable NAMES on the left of the colon change; the
`${{ secrets.TF_VAR_KEY }}` on the right stays. In
`.github/workflows/opa-workload-probe.yml` set the address default to
`https://noaa.pam.okta.com` and the team default to
`nos-coastal-modeling-cloud-sandbox`; the connection and role defaults
stay `REPLACE-ME` until stage 10 makes them.

**8e. The first push.** `develop` only: `main` is what `perform` runs
on, and it waits for stage 11.

```sh
just dry                                 # the workflow is not part of the emission, but prove the tree still generates
git add -A && git commit -m "The workflow's values"
git push -u origin develop
sleep 2                                  # GitHub takes a moment to start the run
gh run watch                             # or: gh run list --branch develop
```

Expected (CI_SETUP 3.8 step 1): the `verify` job green -- the release
installs from TestPyPI, the `Justfile` parses, the tree is public-safe.
`live` runs its gate alone and says SKIPPED, because no secret exists
yet (`gh run view --log | grep 'SKIPPED --'`, or the run's web page:
`gh run watch` does not show it); `perform` is skipped whole off
`main`.

**Report:** `stage 8 done`, with the three ids' output and how the run
ended (`gh run view --json conclusion,jobs --jq '.conclusion, (.jobs[] |
"\(.name): \(.conclusion)")'`).

**Since then.** The fix for finding F11 (and two more the walk found)
is released as 0.1.1.dev15; stage 9 starts by taking it.

## Stage 9 -- the new release, then the bootstrap (DAILY_DRIVER 1.8; CI_SETUP 3.0, 3.3, 3.6, 3.7)

Read CI_SETUP.md sections 3.0, 3.3, 3.6 and 3.7 in the tree first. This
is the stage that has never been done for real anywhere: the bootstrap
CREATING roles and a state bucket. Report at each **Report** line; do
not run ahead past 9d's plan.

Before you start, check the AWS keys are still live (`aws sts
get-caller-identity`); refresh them as in stage 3 if not.

**9a. Two repairs to stage 8.**

1. Re-run the CI run that failed on the TestPyPI outage:

   ```sh
   cd /walk/cs-image-system-walk
   gh run rerun 37406191915 && gh run watch 37406191915
   ```

   Expected: `verify` green with every step run. `live` green too,
   but only its gate ran: the other steps show `-`, and the job
   says why. `gh run watch` shows neither the reason nor the job
   summary (finding F20); read it with

   ```sh
   gh run view 37406191915 --log | grep 'SKIPPED --'
   ```

   or on the run's web page, under "live summary". `perform` shows
   `-` with no steps and no summary at all: the whole job is
   skipped, since it runs on `main` alone.

2. The workflow's two OPA variable names came out doubled
   (`..._sandbox_key_key`, `..._sandbox_key_secret`): the placeholder is
   `REPLACE_ME` alone, and the team name goes in its place.

   ```sh
   sed -i 's/cloud_sandbox_key_key/cloud_sandbox_key/; s/cloud_sandbox_key_secret/cloud_sandbox_secret/' .github/workflows/ci.yml
   grep -n 'TF_VAR_' .github/workflows/ci.yml      # four lines: ..._sandbox_key and ..._sandbox_secret, twice each
   ```

**9b. Take release 0.1.1.dev15** (it carries the fixes the walk asked
for: images say which configuration owns them, a group not created yet
is a note, every dotfile is ignored).

```sh
uv tool install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ "cs-image-system==0.1.1.dev15"
uv tool list                               # cs-image-system v0.1.1.dev15  (if it still says dev14: add --reinstall)
cs-image-system init-config .              # expect two REFUSED lines: .gitignore and .csis-version differ
cs-image-system init-config . --force      # "2 written, 50 kept"; your workflow values are kept
git diff --stat                            # .csis-version, .gitignore, and 9a's ci.yml
just validate && just dry
git add -A && git commit -m "Take cs-image-system 0.1.1.dev15; the workflow's variable names" && git push
```

Expected from `just dry`: no refusal about `walk_team` any more (a note,
"declared and not created yet"). The state line may still count
`foreign: 36` until the reference configuration marks its images
(YOUR step on your local machine, written out before 9g); a dry run
does not refuse on it.

**Report:** `stage 9b done`, and what `gh run watch` and `just dry`
said.

**9c. The secret files.** The interview will offer
`_uncommitted/secrets` INSIDE the repository, and the tree's
`.gitignore` does not ignore `_uncommitted/` (finding F18). Keep them
in the container's home instead:

```sh
mkdir -p ~/walk-secrets && chmod 700 ~/walk-secrets
```

One file per secret, named exactly after it. The commands that read a
value start with a SPACE.

| File | What goes in it |
| --- | --- |
| `OKTA_API_PRIVATE_KEY` | the services app's private key, PEM: a copy of the file your `.envrc` names |
| `TF_VAR_KEY` | ` printf '%s' "$TF_VAR_nos_coastal_modeling_cloud_sandbox_key" > ~/walk-secrets/TF_VAR_KEY` |
| `TF_VAR_SECRET` | ` printf '%s' "$TF_VAR_nos_coastal_modeling_cloud_sandbox_secret" > ~/walk-secrets/TF_VAR_SECRET` |
| `CSIS_CONFIG_IDENTITY` | CI's OWN age identity, made now (CI_SETUP 3.6), below |

`AWS_ROLE_ARN` and `AWS_APPLY_ROLE_ARN` need no file: the script reads
them from the applied root. The GCP and proof-key secrets have no file
and are skipped by name.

CI's identity (3.6), as a second recipient:

```sh
age-keygen -o ~/walk-secrets/CSIS_CONFIG_IDENTITY        # prints "Public key: age1..."
```

Add that public key as a SECOND line under `encryption:` /
`recipients:` in `cfg/_config.yml` (keep yours), then:

```sh
just cli reencrypt
chmod 600 ~/walk-secrets/*
git add -A && git commit -m "CI's age identity is a recipient"
```

**9d. The interview.** `just bootstrap`. Each question shows its
default; press Enter to take it unless the table says otherwise. A
question the table does not list: take the default if it is plainly
right, otherwise stop and ask.

The interview has FOUR sections, and each opens by asking whether you
want it (`[Y/n]`, the capital is the default). The walk's answers are
yes, yes, **no**, yes:

**Section: GitHub** -- "Do you want the GitHub section?" answer `y`
(the repository's branches, ruleset, Actions settings and the
secrets script).

| Question | Answer |
| --- | --- |
| The GitHub repository | `infrastructurebuilder/cs-image-system-walk` |
| The default branch | **`develop`** (the offer may be `master`: GitHub's default today) |
| The branch the perform job runs on | `main` |
| Protect the production branch | `y` |
| PERFORM_RUNTIME | `aws-main` |
| GUARD_RUNTIME | empty |
| AWS_REGION | `us-east-2` |
| The directory holding one file per secret | **`/home/mykel.alvis/walk-secrets`** |

**Section: AWS** -- "Do you want the AWS section?" answer `y`
(the two roles CI assumes, and the state bucket).

| Question | Answer |
| --- | --- |
| The AWS account id | `514190660293` |
| The region; the profile | `us-east-2`; `noaa` |
| The branch the WRITE role trusts | `main` |
| Which OIDC subject forms | **`ids`** (stage 8c: this repository's tokens carry the id-bearing subject) |
| The owner's id; the repository's id | `50206755`; `1405776703` |
| Does the account already have the GitHub OIDC provider | `y` (it asks the account; the reference configuration uses it) |
| The READ-ONLY role's name | **`csis-walk-readonly`** (NOT the default, which is the reference configuration's role) |
| Does the READ-ONLY role already exist | `n` |
| Other subjects the READ-ONLY role keeps trusting | empty |
| The WRITE role's name | **`csis-walk-apply`** |
| Does the WRITE role already exist | `n` |
| Other subjects the WRITE role keeps trusting | empty |
| The state bucket; prefix; region | `csis-walk-tfstate-514190660293`; `statefiles/cs-image-system-walk/`; `us-east-2` |
| Does the state bucket already exist | `n` (the bootstrap makes it) |
| The instance profile | `AmazonSSMRoleForInstancesQuickSetup` |
| Does that instance profile already exist | `y` |
| Tags | the default |

**Section: GCP** -- "Do you want the GCP section?" answer **`n`**
(the workload identity pool and service accounts; the GCE leg is
stage 15). It asks nothing more.

**Section: Okta and OPA** -- "Do you want the Okta and OPA section?"
answer `y` (it creates nothing: it CHECKS the workload connection,
the role and the Okta app, and lists what is still by hand).

| Question | Answer |
| --- | --- |
| The group builder; org; base domain; team; API host | `opa-groups`; `noaa`; `okta.com`; `nos-coastal-modeling-cloud-sandbox`; `https://noaa.pam.okta.com` |
| The branch the workload role is pinned to | `main` |
| The OPA workload connection | **`github-cs-image-system-walk`** (it does not exist yet; stage 10 makes it) |
| The OPA workload role | **`cs-image-system-walk-ci`** |
| every "Does ... exist / Is it ..." question after those | the default it shows (it asks OPA and Okta itself) |

When it ends it prints the `export` lines for the apply and writes
`bootstrap.yaml` and `generated/bootstrap/`. Read
`generated/bootstrap/README.md`: what it made, and under "by hand" the
OPA steps that become stage 10.

**9e. The first apply, on local state.** Run the `export` lines it
printed (`GITHUB_TOKEN` and `AWS_PROFILE` are already in your shell if
`.envrc` has them), then PLAN first:

```sh
cd generated/bootstrap
tofu init
tofu plan
```

Read the plan before anything else. It must say `0 to destroy`. It
should CREATE the two roles with their policies, the bucket with its
versioning, encryption and public-access block, the repository's
default branch, Actions permissions, the ruleset on `main` and two
Actions variables (an empty `GUARD_RUNTIME` is not created) -- 13
resources; it should only READ the OIDC provider and the instance
profile. A 403 from GitHub here names a permission the token
lacks (finding F12): add it to the token and plan again.

```sh
tofu apply                 # type yes after reading the same plan again
cd ../..
```

**Report:** `stage 9e done` with the `Plan:` line and the `Apply
complete!` line, or the error. STOP here.

**9f. The state moves into the bucket -- with a known trap.** The page
says to run `just bootstrap` again, "the bucket now exists, so the root
binds to it", then `tofu init -migrate-state`. Reading the code says
two things the page does not (finding F17), and this step finds out
whether they are true:

- the second interview does NOT notice the bucket by itself: "Does the
  state bucket already exist?" still offers `n`, and you must answer
  `y`;
- answering `y` tells the root the bucket is someone else's, so the
  next plan would DESTROY the bucket's versioning, encryption and
  public-access block, and then fail on the bucket itself.

```sh
just bootstrap             # Enter at every question EXCEPT: "Does the state bucket already exist?" -> y
cd generated/bootstrap
tofu init -migrate-state   # yes, copy the state to the bucket
tofu plan                  # PLAN ONLY. Do not apply.
```

**Report:** `stage 9f plan` with the `Plan:` line and every line that
says `will be destroyed`. Never apply a plan here that destroys
anything.

**What happened (2026-10-06): `Plan: 0 to add, 0 to change, 4 to
destroy`.** The prediction held: finding F17 is confirmed. The way
out makes the root FORGET the bucket's four resources; nothing in
AWS is touched, and the bucket keeps its versioning, encryption and
public-access block.

```sh
cd /walk/cs-image-system-walk/generated/bootstrap
aws sts get-caller-identity                 # keys live?
tofu state list | grep aws_s3_bucket        # exactly the four addresses below
tofu state rm \
  'module.bootstrap_aws.aws_s3_bucket_public_access_block.state[0]' \
  'module.bootstrap_aws.aws_s3_bucket_server_side_encryption_configuration.state[0]' \
  'module.bootstrap_aws.aws_s3_bucket_versioning.state[0]' \
  'module.bootstrap_aws.aws_s3_bucket.state[0]'
tofu plan                                   # must end: No changes.
aws s3 ls s3://csis-walk-tfstate-514190660293/statefiles/cs-image-system-walk/   # bootstrap.tfstate is in the bucket
cd ../..
```

From here the bucket is the walk's but no root manages it, like the
reference configuration's: at teardown it is emptied and removed by
hand. The local `terraform.tfstate` and its `.backup` beside the root
are leftovers of the first apply (the root reads the bucket now);
leave them until Claude says, they are ignored by git.

**Report:** `stage 9f done` with the last line of that `tofu plan`
and the `aws s3 ls` line.

**On your local machine (the host, NOT the container), before 9g:
the reference configuration marks its images.** Not in the container,
and not in the walk tree: this is one command in the OTHER
configuration repository, in its checkout on your local machine, and
it is yours because it writes to AWS.

Why: release 0.1.1.dev15 tags every NEW image with the configuration
that owns it (`csis_config`), and a configuration ignores images
tagged for another. The reference configuration's 36 images were
baked before that, so they carry no such tag, and the walk's state
query still counts them `foreign: 36`. A dry run only reports that;
the STRICT state query in CI's `live` job fails on it. The relabel
writes the one missing tag on each of the 36. It changes nothing
else about any image and nothing in either tree.

```sh
aws sso login --profile noaa                 # your local machine's own AWS session
cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-testconfig    # the reference configuration's checkout (this walk's path)
source .envrc && export AWS_PROFILE=noaa
just cloud-relabel aws-east2-runtime         # dry: "36 image(s) would be relabelled"
just cloud-relabel aws-east2-runtime no      # writes csis_config=cs-image-action-test on the 36
just cloud-relabel aws-east2-runtime         # dry again: nothing left to relabel
```

Then, still on your local machine and in that checkout, move the
reference configuration's `main` to its `develop` (which is on dev15,
CI green), so its own CI runs the release that ignores the WALK's
images once the walk bakes:

```sh
git fetch origin && git push origin origin/develop:main
```

That push starts its `perform` job; nothing is due to bake there.

**Report:** `relabel done` (and `reference main moved`). Claude
confirms both before you push in 9g.

**9g. The secrets, and the push** (after 9f is settled):

```sh
cd /walk/cs-image-system-walk
bash generated/bootstrap/set-secrets.sh        # sets six; says "skipped" for the four with no file
gh secret list                                 # names only
just dry                                       # regenerates generated/bootstrap from bootstrap.yaml
git add -A && git status --short               # bootstrap.yaml and generated/bootstrap/ are committed; no secret file is listed
git commit -m "The bootstrap: roles, state bucket, repository settings" && git push
sleep 2                                        # GitHub takes a moment to start the run
gh run watch
```

Expected: `verify` green, and `live` now RUNS, because its secrets
exist. `live` is green only once the relabel above is done (`just
dry` then says `foreign: 0`); `perform` still waits for `main`, which
is stage 11.

**Report:** `stage 9 done`, with `gh run view --json conclusion,jobs
--jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'`.

## Stage 10 -- OPA: the workload objects, the first real run, the probe (CI_SETUP 3.5; DAILY_DRIVER 3.1)

Read CI_SETUP.md section 3.5 and the daily driver's 3.1 first. The
"By hand, still" list in `generated/bootstrap/README.md` says the same
steps with your names in them.

This stage makes the walk's first real changes outside AWS and GitHub:
two objects you create in the OPA console, and then the system creates
the walk's group in OPA. Everything it creates is named `walk_team_...`;
nothing of the reference configuration's is touched. The system never
destroys an OPA group, so these are removed by hand at teardown
(decision W3).

**10a. The workload connection, as a DRAFT** (you, in the OPA console;
it needs the DevOps-admin role). DevOps Administration, Workload
connections, Create Workload Connection:

| Field | Value |
| --- | --- |
| Type | GitHub Actions |
| GitHub Owner | `infrastructurebuilder` |
| Name | `github-cs-image-system-walk` |
| Token TTL | 1 hour |
| JWKS URL | `https://token.actions.githubusercontent.com/.well-known/jwks` (if the form did not fill it) |
| Required claim | `repository` Equals `infrastructurebuilder/cs-image-system-walk` |
| Required claim | `repository_owner` Equals `infrastructurebuilder` |
| `ref` claim | none here |

Create it. Do NOT activate it yet.

**10b. The workload role** (you; it needs the security-admin role).
Security Administration, Workload roles: name
`cs-image-system-walk-ci`, the connection above selected, no
conditions yet. Do not create any security policy by hand: the system
makes one per group.

**10c. The names into the tree, and the first real run.**

1. In `cfg/group-builders.yml`, on the `opa-groups` builder, beside
   `team:`, add:

   ```yaml
       workload_connection: "github-cs-image-system-walk"
       workload_role: "cs-image-system-walk-ci"
   ```

2. In `.github/workflows/opa-workload-probe.yml`, replace the two
   remaining `REPLACE-ME` defaults: `connection` becomes
   `github-cs-image-system-walk`, `role` becomes
   `cs-image-system-walk-ci`.
3. In `cfg/_config.yml`, set `apply_identity: true` (a convergent flag,
   safe to leave on: it applies only what the YAML says, and the gate
   refuses destroys). Leave `apply_storage` and `apply_instances`
   `false`.
4. The rhythm of section 3: validate, dry, read the script, run.

   ```sh
   cd /walk/cs-image-system-walk
   aws sts get-caller-identity                # keys live? the roots' state is in the bucket
   just validate
   just dry identity
   tail -5 generated/identity/run-identity.sh # it now ends with apply-check and tofu apply
   just run identity
   ```

What `just run identity` does, for real: looks your user up in Okta,
then plans, gates and applies the group root. Expected in its output:

- a `Plan:` line with only additions, `0 to destroy`: the OPA groups
  `walk_team_user` and `walk_team_admin`, your membership as an admin,
  the resource group `walk_team_rg`, the project `walk_team_rg_login`
  with its enrollment token, and the policies
  `walk_team_v1_security_policy_user` and `..._admin`;
- the gate's verdict, then `Apply complete!`;
- a line `Group walk_team: CI login policy
  walk_team_v1_security_policy_ci created` (it copies the user policy
  for the workload role; if the role of 10b is missing it says `NOT
  reconciled` and the run still ends);
- `Run ... completed: identity` and a meta-state commit.

Then:

```sh
git push
just state-query                            # walk_team: admins, a gid, the token live, the CI policy; a note that the connection is a DRAFT
```

**Report:** `stage 10c done` with the `Plan:` line, the `CI login
policy` line and the last line of the run; or the error. STOP here.

**10d. The probe.** It presents this repository's GitHub token to the
draft connection and stops; against a draft OPA validates the token and
issues nothing usable.

```sh
gh workflow run opa-workload-probe.yml --ref develop
sleep 2                                     # GitHub takes a moment to start the run
gh run watch                                # pick the "OPA workload probe" run
gh run view --log | grep -iE 'claim|verdict|valid|refus|error' | tail -20
```

Green is the proof the claims match.

**10e. Activate the connection** (you, in the console). From here the
system refuses the login proof when either object is absent or the
connection is still a draft.

**10f. Let the bootstrap check again.** `just bootstrap`, Enter at
every question (the Okta section asks OPA again; the bucket question
now offers `y`). Then:

```sh
just dry
git add -A && git commit -m "The workload connection and role are named and stand" && git push
```

`generated/bootstrap/README.md` should now say the connection exists,
is active, and that the builder names both.

The branch pin on the role (`ref` Equals `refs/heads/main`, CI_SETUP
3.5 step 6) comes after the first green login proof from `main`, in
stage 12.

**Report:** `stage 10 done` with how the probe ended and what the
README's okta lines say.

## Stage 11 onward -- written when you reach them

These stages depend on what the earlier ones produce (the bootstrap's
interview, the names it prints), so their exact commands are added to
this page as each one comes up. The order, and the page each follows:

| Stage | What | Follows |
| --- | --- | --- |
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

- **A copy of your local machine's Application Default Credentials**
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
--no-launch-browser`, which prints a URL to open in a browser on your
local machine). Not what you asked for, listed for completeness.

**For the walk's GCE leg (stage 15)** the recommendation is way 2 with
a copy of your local machine's ADC file: it is the same identity your
local machine already uses, it creates nothing, and it serves every
tool. You place the file in the container's home yourself; it never
goes on the volume and Claude does not open it. IAP sessions
additionally need an SSH key in the container without a passphrase;
that is set up at stage 15.

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
| F8 | every YAML file of a starter opens with a comment naming its path in the SYSTEM repository (`docs/examples/standard-aws/...`) and a relative link (`../../../CONFIGURATION.md`) that points nowhere in a team's own tree | words |
| F9 | 1.7 says "the recipes assume no direnv, so every session starts `source .envrc`"; the operator wants direnv, and the page neither offers it nor says what an `.envrc` for it needs (`direnv allow` after each edit) | words |
| F10 | a missing OPA credential ends `validate` with a 60-line traceback under a good one-line message; and section 6's row quotes a message (`OPA credentials for team '<t>' not found in the environment`) the system does not print (`Okta builder <b> is missing a key value. Expected to find environment variable TF_VAR_<team>_key ...`) | code and words |
| F11 | two configurations in one account see each other's images as `foreign` (no tag says whose an image is): the walk's first state query reported the reference configuration's 36 AMIs | code: stage 82 |
| F12 | no page says which permissions a fine-grained GitHub token needs; CI_SETUP 3.0 names `GITHUB_TOKEN` and the bootstrap suggests `$(gh auth token)`, which assumes a browser login | words |
| F13 | CI_SETUP 3.2 step 4's third command (`gh api orgs/<owner>/actions/oidc/customization/sub`) answers 403 to a repository-scoped fine-grained token; the page offers no repository form | words |
| F14 | a declared group that was never created is hard `missing`, so a new tree refuses every run after its first | code: fixed in dev15 |
| F15 | the starter's `.gitignore` names a few secret files, not the shape of one: a token dropped beside the tree is one `git add -A` from a commit | starter: fixed in dev15 |
| F16 | a tree pinned to a development release cannot pass even `verify` while TestPyPI is down | words |
| F17 | the bootstrap's create path: the second interview does not notice the bucket it made, and answering that it exists plans the destruction of the bucket and its protections. CONFIRMED live at stage 9f: the second interview offered `Does the state bucket already exist? [y/N]`, and after `y` the plan said `0 to add, 0 to change, 4 to destroy` | code |
| F18 | the interview's default secrets directory, `_uncommitted/secrets`, is inside the tree and not ignored by the starter's `.gitignore` | starter |
| F19 | nothing checks the workflow's `TF_VAR_<team>_*` names against the group builder's team: a doubled suffix was pushed unnoticed | code, minor |
| F20 | the pages say "read the job summary" but not where: `gh run watch` shows neither the summary nor the gate's `SKIPPED` line, and a skipped `perform` job has no summary at all | words |
| F21 | the starter workflows are ageing: `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19 (unproved there), five actions target the deprecated Node 20, and `setup-uv`'s cache key matches no file in a configuration repository | starter: hygiene XII item 7 |
