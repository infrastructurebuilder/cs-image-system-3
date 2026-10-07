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

From stage 11d on, every box also PROVES where it is before it does
anything: its first line prints `OK: ...` or `STOP: ...`. If it
prints `STOP`, you are in the other place: run nothing below it.
(On 2026-10-07 a container box was typed into a local terminal that
stood in the system repository, and a local box was run on the wrong
branch; nothing was lost, and both are findings: F31 and F32.)

**Watching CI.** After a `git push` or a `gh workflow run`, GitHub
takes several seconds to register the run. So this page never asks you
to wait and look: its commands wait themselves, asking every five
seconds for up to a minute until the run for the commit you just
pushed exists, and only then watch it. Wherever a push is followed by
CI, these are the lines:

```sh
run=""
for i in $(seq 12); do
  sleep 5
  run=$(gh run list --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  [ -n "$run" ] && break
done
echo "run ${run:-NOT FOUND after 60 seconds}"
[ -n "$run" ] && gh run watch "$run"
```

They never call `gh run watch` without a run, so `gh` never shows its
chooser of recent runs (which look alike). If they print `run NOT
FOUND after 60 seconds`, no run started for that commit: the push did
not trigger the workflow, and that is worth reporting. `$run` stays
set for the `gh run view "$run"` lines that follow. Never run a bare
`gh run watch` or `gh run view`; if you are ever at the chooser
anyway, the right run is the TOP one whose title is your last
commit's message.

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
run=""
for i in $(seq 12); do
  sleep 5
  run=$(gh run list --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  [ -n "$run" ] && break
done
echo "run ${run:-NOT FOUND after 60 seconds}"
[ -n "$run" ] && gh run watch "$run"
```

Expected (CI_SETUP 3.8 step 1): the `verify` job green -- the release
installs from TestPyPI, the `Justfile` parses, the tree is public-safe.
`live` runs its gate alone and says SKIPPED, because no secret exists
yet (`gh run view "$run" --log | grep 'SKIPPED --'`, or the run's web page:
`gh run watch` does not show it); `perform` is skipped whole off
`main`.

**Report:** `stage 8 done`, with the three ids' output and how the run
ended:

```sh
gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
```

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
run=""
for i in $(seq 12); do
  sleep 5
  run=$(gh run list --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  [ -n "$run" ] && break
done
echo "run ${run:-NOT FOUND after 60 seconds}"
[ -n "$run" ] && gh run watch "$run"
```

Expected: `verify` green, and `live` now RUNS, because its secrets
exist. `live` is green only once the relabel above is done (`just
dry` then says `foreign: 0`); `perform` still waits for `main`, which
is stage 11.

**Report:** `stage 9 done`, with:

```sh
gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
```

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

**Where stage 10 stands (2026-10-07).** The stage was interrupted
twice by defects in the system, each fixed by a release, so its text
is longer than its work and its boxes are not all still to do:

| Part | State |
| --- | --- |
| 10a, 10b | done |
| 10c, steps 1-3 (the three edits) | done, committed and pushed |
| 10c, step 4 (the run) | failed twice: F22 on 0.1.1.dev15, F24 on 0.1.1.dev16 |
| 10d, 10e | done |
| the releases 0.1.1.dev16 and 0.1.1.dev17 | cut; both are on the index |
| "10c, the run, on 0.1.1.dev17" | done 2026-10-07: `walk_team` exists in OPA; CI green |
| "The reference configuration's proof" (your local machine) | done 2026-10-07: `No changes`; its `main` is on 0.1.1.dev17 |
| 10f | done 2026-10-07: a third interview changed only the Okta section's words; CI green |

**Stage 10 is DONE (2026-10-07).** Every box below is the record of
what happened; your next command is in stage 11.

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

**10c. The names into the tree, and the first real run.** (Steps 1-3
are DONE and pushed. Step 4's run is NOT repeated from here: it needs
a newer release than this box installs. Go to "10c, the run, on
0.1.1.dev17" below, which installs the release and then runs.)

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

**What happened (2026-10-07): the run FAILED, and it was the system's
fault** (finding F22). The plan looks the group's gid up in OPA
before the group exists, finds none (`export-gids: identity plugin
'okta' reported no gid for groups ['walk_team']`), and stops. Nothing
was created. No release before 0.1.1.dev16 can create a new OPA group;
the fix is being released. Until then:

- leave the tree as it is, with 10c's three edits uncommitted;
- do 10d and 10e below now: neither needs the group;
- when Claude says dev16 is out, the box "10c again, on 0.1.1.dev16"
  after 10e takes the release and repeats the run.

**10d. The probe.** It presents this repository's GitHub token to the
draft connection and stops. (The guide says a draft "issues nothing
usable"; when this was run, the draft did return a token: finding
F23.)

```sh
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)          # only a run created after this is the one you dispatch
gh workflow run opa-workload-probe.yml --ref develop \
  -f connection=github-cs-image-system-walk -f role=cs-image-system-walk-ci
run=""
for i in $(seq 12); do
  sleep 5
  run=$(gh run list --workflow opa-workload-probe.yml --limit 1 --json databaseId,createdAt --jq "[.[] | select(.createdAt >= \"$start\")][0].databaseId // empty")
  [ -n "$run" ] && break
done
echo "run ${run:-NOT FOUND after 60 seconds}"
[ -n "$run" ] && gh run watch "$run"
gh run view "$run" --log | grep -iE 'claim|verdict|valid|refus|error' | tail -20
```

Green is the proof the claims match.

**10e. Activate the connection** (you, in the console). From here the
system refuses the login proof when either object is absent or the
connection is still a draft.

**On your local machine (the host, NOT the container): cut release
0.1.1.dev16.** (DONE 2026-10-07.) The fix for F22 is merged to the system repository's
`develop` (stage 84); a release carries it to the walk. This is the
system repository's checkout, not the walk tree:

```sh
cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3      # the system repository (this walk's path)
git checkout develop && git pull
git status --short                                         # nothing listed
curl -s -o /dev/null -w '%{http_code}\n' https://test.pypi.org/legacy/   # 200: the index can take an upload
just release dev test yes                                  # dry: it would cut 0.1.1.dev16
just release dev test                                      # the bar (about 25 minutes), the upload, the commit, the tag
git push --follow-tags
git checkout feature/walk-daily-driver                     # brings this document back
```

While you are on `develop` this document is not in the working tree;
that is expected. The `curl` line is the check stage 83 will build
into the release: if it does not print 200, do not start.

**Report:** `dev16 pushed`. Claude then confirms the release on the
index and takes it into the reference configuration.

**10c again, on 0.1.1.dev16.** (DONE 2026-10-07: it failed, see
below. Do not repeat it; 0.1.1.dev17 replaces it.) In the container:

```sh
cd /walk/cs-image-system-walk
uv tool install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ "cs-image-system==0.1.1.dev16"
uv tool list                               # cs-image-system v0.1.1.dev16
cs-image-system init-config . --force      # .csis-version; anything else it names
aws sts get-caller-identity                # keys live?
just validate
just dry identity
just run identity
```

The plan now defers the gid lookup (`group_gids` shows `(known after
apply)`), the apply creates the group and THEN reads its gid; if OPA
needs a moment to assign one the run says `OPA carries no gid yet
... asking again` for up to 30 seconds. Everything else is as 10c
says, including its Report line.

**What happened (2026-10-07): the run FAILED again, one step earlier,
and again it was the system's fault** (finding F24). Before it plans,
the identity runner asks the root's terraform state which attachments
are stale (the `prune-attachments` line). A tree that has never
applied has no state at all; `tofu state list` then answers `No state
file was found!`, and the step took that for a failure. Nothing was
created and nothing was removed. The reference configuration never met
this: its roots had state long before the prune step existed. The fix
(stage 85: no state yet means nothing to prune) is in 0.1.1.dev17.
Leave the tree as it is.

**On your local machine (the host, NOT the container): cut release
0.1.1.dev17.** (DONE 2026-10-07.) The dev16 box above, one number
on; again the system repository's checkout, not the walk tree:

```sh
cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3      # the system repository (this walk's path)
git checkout develop && git pull
git status --short                                         # nothing listed
git log --oneline -1                                       # the stage 85 squash: "The first identity apply ... nothing to prune"
curl -s -o /dev/null -w '%{http_code}\n' https://test.pypi.org/legacy/   # 200: the index can take an upload
just release dev test yes                                  # dry: it would cut 0.1.1.dev17
just release dev test                                      # the bar (about 25 minutes), the upload, the commit, the tag
git push --follow-tags
git checkout feature/walk-daily-driver                     # brings this document back
```

**Report:** `dev17 pushed`. Claude then confirms the release on the
index and takes it into the reference configuration.

**10c, the run, on 0.1.1.dev17.** (DONE 2026-10-07; what happened
is under its Report line.) In the container. The release is
out (all 18 packages are on the index, 2026-10-07). 10c's three edits
are already in the tree and pushed; what is left is its step 4, the
run, and the new release comes first.

1. Take the release. The tool in the container is still 0.1.1.dev16
   and `.csis-version` says the same; these lines move both:

   ```sh
   cd /walk/cs-image-system-walk
   uv tool install --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ "cs-image-system==0.1.1.dev17"
   uv tool list                               # cs-image-system v0.1.1.dev17
   cs-image-system init-config . --force      # writes .csis-version; names anything else it writes
   cat .csis-version                          # 0.1.1.dev17
   ```

   If `uv tool list` or `cat` still shows dev16, stop and say so.

2. The run, with the rhythm of section 3:

   ```sh
   aws sts get-caller-identity                # keys live? the roots' state is in the bucket
   just validate
   just dry identity
   just run identity
   ```

   Where the last run stopped, this one says `the root has no state
   yet (its first apply); nothing to prune` and goes on. Then, as 10c
   describes it:

   - a `Plan:` line with only additions and `0 to destroy`, in which
     `group_gids` shows `(known after apply)`: the gid lookup now
     waits for the group;
   - the gate's verdict, then `Apply complete!` (if OPA needs a
     moment to assign the gid the run says `OPA carries no gid yet
     ... asking again`, for up to 30 seconds);
   - a line `Group walk_team: CI login policy
     walk_team_v1_security_policy_ci created`;
   - `Run ... completed: identity` and a meta-state commit.

   If the run fails, STOP and paste the error. Do not go on to step 3.

3. Record it and let CI look. The run committed `generated/` and
   `meta-state/` itself. The version pin is yours to commit, and CI
   installs the release that file names, so it must go with them:

   ```sh
   git status --short                         # expect exactly one line: M .csis-version
   git add .csis-version && git commit -m "Take release 0.1.1.dev17"
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   just state-query                           # walk_team: admins, a gid, the token live, the CI policy
   ```

   If `git status --short` lists anything besides `.csis-version`,
   paste it before you commit.

**Report:** `stage 10c done` with the `Plan:` line, the `CI login
policy` line, the last line of the run, and what the `gh run view`
line printed; or the error.

**What happened (2026-10-07): it worked.** `Plan: 8 to add, 0 to
change, 0 to destroy`, then `Group walk_team: CI login policy
walk_team_v1_security_policy_ci created` and `Run
2026_10_07t13_47_50_739856 completed: identity`. The walk's first
group exists in OPA: stages 84 and 85 are proved by the run they
were written for. The run's own commit (8618631) and the version pin
(b400eb3) are pushed; CI run 37631775218 is green on them, installed
0.1.1.dev17 from the index, and its strict state query said `no
drift: meta-state agrees with reality`.

**On your local machine (the host, NOT the container): the reference
configuration's proof.** The two fixes must have changed nothing for
a tree whose groups already stand. The reference configuration's
`develop` is on 0.1.1.dev17 (Claude did that, 2026-10-07; b65b6c6,
its CI green). Both steps are yours: the first is a real run there
and the second moves its `main`.

1. (DONE 2026-10-07: `No changes`; what happened is under the
   Report line.) Run its identity lifecycle for real, and read the
   plan:

   ```sh
   aws sso login --profile noaa                 # your local machine's own session; it HAD lapsed when this was written
   cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-testconfig    # the reference configuration's checkout (this walk's path)
   git status -sb                               # develop; nothing listed under it
   git pull --ff-only                           # Already up to date.
   source .envrc && export AWS_PROFILE=noaa
   just run identity
   ```

   That tree has ONE identity root (`oktagroups`), so there is one
   plan. Expect, in this order:

   - `every membership attachment in state is still declared;
     nothing to prune`: the prune step lists a state that exists, as
     it always has;
   - `No changes. Your infrastructure matches the configuration.`:
     the five groups stand, so their gids are read at plan time
     exactly as before;
   - the gate's verdict (`Plan passes the apply gate.`), then the
     apply. In THIS tree you will not see tofu's `Apply complete!
     Resources: 0 added, 0 changed, 0 destroyed.` line (finding F25):
     the log shows the last 40 lines of each command's output, tofu
     prints that line BEFORE the root's outputs, and this root's
     outputs are exactly 40 lines. What you see is `tofu apply stdout
     (last 40 of 45 lines; all at DEBUG)` and then the outputs
     (`group_gids`, `groups`). The plan's `No changes` is the
     evidence that nothing was applied;
   - five lines `Group <name>: CI login policy ... unchanged`,
     warnings that the other lifecycles' scripts were SKIPPED (they
     were not requested), `Meta-state committed as ...`, the run's
     summary, and `Run ... completed: identity`.

   If the plan says anything but `No changes`, STOP: do not do step
   2, and paste the `Plan:` line with the resource lines above it. It
   would mean a fix altered a standing tree. Know that the run does
   not wait for you: `apply_identity` is on in that tree (as it is
   for its CI), so a plan with additions or changes is applied as it
   is shown; the gate refuses destroys.

2. (DONE 2026-10-07: the reference's `develop` and `main` are both
   682b41c.) Only after `No changes`: push the run's record and move
   `main`.

   ```sh
   git push
   git fetch origin && git push origin origin/develop:main
   ```

   The second line starts the reference's `perform` job on
   0.1.1.dev17; nothing is due to bake there.

**Report:** `reference identity: no changes` and `reference main
moved`; or the plan you saw.

**What happened at step 1 (2026-10-07): no changes.** The plan read
the five gids at plan time (`data.external.group_gids: Read
complete`), said `No changes. Your infrastructure matches the
configuration.`, passed the gate and applied nothing; each group's
CI login policy was `unchanged`; `Run 2026_10_07t09_03_31_416124
completed: identity`, its record committed as 682b41c. The run's
summary counts `stale: 3` and `unavailable: 1`: both stood before
the run (the dry run that took dev17 counted the same) and neither
is drift. Neither fix altered a standing tree. Step 2 is what is
left.

This page had promised an `Apply complete! ... 0 destroyed` line
there, and the operator did not find it: the page was wrong about
what the log shows, not the run about what it did. That is finding
F25, and step 1's list above now says what is really printed.

**10f. Let the bootstrap check again.** In the container. The
interview of 9d asks everything once more, and this time you change
nothing: press Enter at every question. What moves is the Okta and
OPA section, whose yes/no questions are not remembered answers but
what OPA says NOW, and OPA now has the connection, the role and the
group builder's names.

1. The interview:

   ```sh
   cd /walk/cs-image-system-walk
   aws sts get-caller-identity                # keys live?
   just bootstrap
   ```

   Enter at every question, and READ the yes/no ones as they pass.
   The capital letter in the brackets is what Enter takes. They come
   in this order (the questions between them show a name or an id;
   Enter keeps it):

   | The question | Brackets | Why |
   | --- | --- | --- |
   | Do you want the GitHub section? | `[Y/n]` | as before |
   | Protect the production branch with a ruleset ...? | `[Y/n]` | as before |
   | Do you want the AWS section? | `[Y/n]` | as before |
   | Does the account already have the GitHub OIDC identity provider ...? | `[Y/n]` | as before |
   | Does the READ-ONLY role already exist (it is then adopted by import)? | `[y/N]` | your answer of 9d, remembered. The role exists NOW because this root made it, and "no" is what keeps it this root's |
   | Does the WRITE role already exist (it is then adopted by import)? | `[y/N]` | the same |
   | Does the state bucket already exist? | `[Y/n]` | your `y` of 9f, remembered |
   | Does that instance profile already exist? | `[Y/n]` | as before |
   | Do you want the GCP section? | `[y/N]` | as before |
   | Do you want the Okta and OPA section? | `[Y/n]` | as before |
   | Does the group builder already name that connection and role? | `[Y/n]` | was no: 10c step 1 |
   | Does that workload connection exist? | `[Y/n]` | was no: 10a |
   | Does it require `repository` and `repository_owner` to be this repository's? | `[Y/n]` | a new question: asked only of a connection that exists |
   | Is it ACTIVE (not a draft)? | `[Y/n]` | new: 10e |
   | Does that workload role exist? | `[Y/n]` | was no: 10b |
   | Is the role bound to that connection? | `[Y/n]` | new |
   | Is the role pinned to the production branch ...? | `[y/N]` | new; the pin comes in stage 12 |
   | Does the Okta API services app authenticate with its private key and scopes? | `[Y/n]` | as before |
   | Were its granted scopes read scopes only (no *.manage)? | `[Y/n]` | as before |
   | Can the app read its own record ...? | `[y/N]` | as before |

   If a question shows brackets other than the table's, do NOT type
   the answer you expected: press Ctrl-C (nothing is written until
   the last question is answered) and paste the question as it was
   shown. A wrong default is a finding, and for the two role
   questions a typed `y` would turn roles this root made into roles
   it adopts. An Okta-section question that shows `[y/N]` where the
   table says `[Y/n]` most likely means OPA could not be asked: the
   interview then falls back to the old answer.

   It ends with `bootstrap: answers in bootstrap.yaml; sections
   wanted: aws, github, okta` and the files it wrote.

2. What changed must be the Okta section's words and nothing else:

   ```sh
   git status --short                         # expect two lines: M bootstrap.yaml and M generated/bootstrap/README.md
   git diff --stat -- generated/bootstrap     # only README.md: no .tf, no tfvars, no set-secrets.sh
   grep -n -A3 '^- \*\*okta\*\*' generated/bootstrap/README.md
   ```

   The `grep` prints the heading and three lines. Two have changed:
   the connection `exists (active: yes; requires this repository:
   yes)`, and the role `exists (bound to ...: yes; pinned to `main`:
   no); named on `opa-groups`: yes`. The third is the Okta API
   services app's, and it reads as it did before: `authenticates
   with its key; read scopes only: yes; its own record readable:
   no`. That `no` is expected and is not a fault: the app holds only
   read scopes for users and groups, so it cannot read its own
   record (the README's "By hand, still" list keeps the request to
   the org's Okta admins that follows from it). If `git status`
   lists any other file under `generated/bootstrap/`, stop and paste
   it: the root itself would have changed, and nothing in this stage
   should change it.

3. Record it and let CI look:

   ```sh
   just dry
   git add -A && git commit -m "The workload connection and role are named and stand"
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   ```

   `just dry` is a dry run of every lifecycle, so the commit also
   carries its regenerated emission and records.

The branch pin on the role (`ref` Equals `refs/heads/main`, CI_SETUP
3.5 step 6) comes after the first green login proof from `main`, in
stage 12. The short form of this check, for another day, is `just
bootstrap --section okta`: it asks only that section and keeps the
others' answers as they are. The walk takes the long form on purpose,
to see that a third interview leaves the root alone.

**Report:** `stage 10 done` with: any question whose brackets
differed from the table (or `brackets as the table`), the lines the
`grep` printed, and what the `gh run view` line printed.

## Stage 11 -- the storage, then the first `perform` on `main` (DAILY_DRIVER 3.2; CI_SETUP 3.8 step 4)

Read the daily driver's 3.2 and the CI guide's 3.8 first. Of 3.8's
five proofs, three are behind you: `verify` and `live` are green on
`develop`, and the probe ran and the connection is active. The
fourth is one `perform`: the job that runs on `main` alone, records,
bakes what is due under the WRITE role, and pushes its records back.
This will be the first time anything bakes in this tree, and the
first time the role the bootstrap made is used for it.

**Why the storage comes first** (finding F26, your decision
2026-10-07). The guide puts the first `perform` before the daily
driver's "Making things". In this tree that order would fail: the
instance `walk-node-1` mounts the storage `data`, so its terraform
root reads the storage root's state, and a performing run PLANS the
instance root even though it does not apply it. The storage has
never been applied, its state does not exist, and the plan would
stop with `Unable to find remote state ... No stored state was found`
after both images had baked. So the storage is made first, by you,
the way 3.2 says; then `perform` has a state to read.

| Part | State |
| --- | --- |
| 11a. The storage | done 2026-10-07: the volume exists, its state is in the bucket, CI green |
| 11b. The first `perform` | ran 2026-10-07 and ended RED in the base image's bake (finding F28); nothing was left behind |
| 11c, steps 1-3 (the records, the base test, CI on `develop`) | done 2026-10-07 |
| 11c, step 4 (the second `perform`) | ran 2026-10-07 and ended RED in the base image's bake again, for another reason (finding F29); nothing was left behind |
| the fix for F29 and F28 (stage 86) | merged 2026-10-07; it needs release 0.1.1.dev18 |
| 11d, first attempt | 0.1.1.dev18 was cut from the walk branch, and step 2 was typed on the local machine (F31, F32); repaired, nothing lost |
| 11d, step 1 (release 0.1.1.dev19 from `develop`) | done 2026-10-07: cut on `develop`, tagged there, all 18 packages on the index; the stray tool is gone from your machine |
| **11d, step 2** (the container: the walk takes 0.1.1.dev19) | **NEXT: start there**, then steps 3 and 4 |

**11a. The storage.** In the container. One 100 GB encrypted gp3
EBS volume named `data`, in the availability zone of the runtime's
subnet. The size and type are the starter's, in
`cfg/storage-builders.yml` (`size: 100`); if you want another size,
change it BEFORE step 2: afterwards it is a change to a standing
volume. It stands until teardown (stage 17).

1. In `cfg/_config.yml`, set `apply_storage: true`. Leave
   `apply_instances` `false`.

2. The rhythm of section 3:

   ```sh
   cd /walk/cs-image-system-walk
   aws sts get-caller-identity                # keys live?
   just validate
   just dry storage
   tail -3 generated/storage/run-storage.sh   # it now ends with gate-plan, apply-check and tofu apply
   just run storage
   ```

   The plan should add ONE resource, the volume (the module holds one
   `aws_ebs_volume`), and destroy nothing; then the gate's verdict,
   the apply, and `Run ... completed: storage` with a meta-state
   commit. Claude has not seen a storage run in this tree, so the
   lines around those are not promised: paste the `Plan:` line as you
   see it. If the run fails, STOP and paste the error; do not go on.

3. Record it and let CI look. The run committed `generated/` and
   `meta-state/` itself; the flag you edited is yours to commit:

   ```sh
   git status --short                         # expect exactly one line: M cfg/_config.yml
   git add cfg/_config.yml && git commit -m "The storage is applied: apply_storage on"
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch develop --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   just state-query --strict                  # the storage `data` present and recorded; no drift
   ```

   If `git status --short` lists anything besides `cfg/_config.yml`,
   paste it before you commit.

**Report:** `stage 11a done` with the `Plan:` line, the last line of
the run, what the `gh run view` line printed and the last line of
the state query; or the error.

**What happened at steps 1-2 (2026-10-07): it worked.** `Plan: 1 to
add, 0 to change, 0 to destroy`; run `2026_10_07t15_26_24_332664`,
its record committed as 446c70c. AWS has the volume: `data`, 100 GB,
gp3, encrypted, `available`, in us-east-2a. `aws_ebs.tfstate` is in
the bucket beside the identity root's, which is what the instance
root's plan needs (F26): Claude has checked it, so you need not wait
for a word between 11a and 11b. If step 3 ends with CI `success` and
a state query that reports no drift, go straight on to 11b and
report both together; if either is anything else, stop and paste it.

**11b. The first `perform`.** In the container. Only after 11a's
step 3 ended with CI `success` and no drift.

GitHub has no `main` branch for this repository yet: the bootstrap
set the default branch and the ruleset that will protect `main`, and
the branch itself comes into being with this push. (The guide says
"merge `develop` into `main`"; with no `main` to merge into, the
first time is a push of `develop` AS `main`, which is the same
fast-forward. The branch `master` you see on GitHub is the one the
repository was created with; nothing uses it. Both are finding F27.)

1. Start it, and watch. The same commit already has a run on
   `develop`, so these lines ask for the run on `main` by name:

   ```sh
   cd /walk/cs-image-system-walk
   git status -sb                             # develop...origin/develop, nothing listed, not ahead
   git push origin develop:main
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   ```

   It is long: two bakes, each a build machine started, provisioned
   and imaged. Claude has not timed this tree; the reference
   configuration's bakes take ten to twenty minutes each. `gh run
   watch` stays on the screen until the run ends. The `perform` job's
   steps, in the order the workflow has them:

   - `The full run, recorded` and `Push the record`: a dry run of
     everything, committed to `main` before anything performs;
   - `The guarded runtime stays out of CI ...`: says no runtime is
     guarded;
   - `Federated AWS credentials, the WRITE role`: the first use of
     `csis-walk-apply`, from `main`;
   - `The runtime performs`: `just cloud-perform aws-main`. It bakes
     the base image `el10`, then the image `team-node` with its two
     modifications and its in-bake tests, then plans and gates the
     instance root (one machine to add, NOT applied: `apply_instances`
     is `false`);
   - `Push what the performing run committed`;
   - `CI logs in through the managed policy`: mints an OPA token as
     the workload, from `main` for the first time, and then finds no
     standing machine to log into: nothing to prove yet;
   - `The full run, recorded again` and `Push the closing record`;
   - `Reality matches the records (state query --strict)`.

   If the run ends red, do NOT re-run it. Paste what this prints, and
   stop (GitHub masks secret values in its logs):

   ```sh
   gh run view "$run" --json jobs --jq '.jobs[] | select(.conclusion == "failure") | .name, (.steps[] | select(.conclusion == "failure") | "  step: \(.name)")'
   gh run view "$run" --log-failed | tail -60
   ```

2. Only after a green run: `develop` takes the records `perform`
   pushed to `main`, so the two branches do not part.

   ```sh
   git fetch origin
   git log --oneline -4 origin/main           # the closing record, the performing run, the first record, then your commit
   git merge --ff-only origin/main
   git push
   grep -E 'build_id:|series:' meta-state/lineage.yaml   # two builds, each its ami id: series el10 and series team-node
   just state-query --strict
   ```

**Report:** `stage 11 done` with what the `gh run view` line
printed, the first three lines of the `git log`, and the last line
of the state query; or the failed step and its log tail.

**What happened at 11b (2026-10-07): the run ended red, and it was
the starter's fault** (finding F28). Run 37645069158 on `main`:
`verify` and `live` green; in `perform`, the record was made and
pushed, the WRITE role was assumed (its first use, and it worked),
and `The runtime performs` started the base image's bake. The build
machine came up, was reached through Session Manager, updated, got
the OPA agent and the SSM agent, and then failed the LAST step, the
base image's own in-bake tests, with one line: `package git is not
installed`. Packer stopped after 5 minutes 24 seconds and removed
the machine, its security group and its key pair; AWS shows no
machine and no image left. The closing record was still pushed, so
`main` is two record commits ahead of `develop`, and its
`meta-state/runs.yaml` says `base-image: failed`.

Why: `cfg/os-builders.yml`, exactly as the starter writes it, tests
the BASE image for the package `git`. Nothing installs git on the
base: the vendor's AlmaLinux 10 image does not carry it, and a base
image takes no modifications. git arrives one level up, in the image
`team-node`, whose playbook installs it and whose own test checks
it. So the base's test asserts something only the image can make
true, and every tree made from this starter fails its first base
bake. You did nothing wrong, and nothing you typed caused it.

One more thing the log shows, which did NOT fail the run (finding
F29): the update's first attempt lost a race for the package
database's lock (`can't create transaction lock`) against the
machine's own boot script, and passed only because the step retries
once.

**11c. The base image's test, then the second `perform`.** In the
container. The test is yours to state: it is a team value in
`cfg/`, which no release rewrites. It should name something the
BASE bake itself puts there. This tree's base declares
`identity_types: [okta]`, so its bake installs the OPA agent's
package, `scaleft-server-tools` (the failed run's log shows it
installed): that is the package to assert.

1. `develop` first takes the two records the failed run pushed to
   `main`, so the branches do not part:

   ```sh
   cd /walk/cs-image-system-walk
   git status -sb                             # develop...origin/develop, nothing listed
   git fetch origin
   git merge --ff-only origin/main            # Fast-forward: two record commits
   ```

2. In `cfg/os-builders.yml`, in the `tests:` of `el10`, change

   ```yaml
         packages: [git]
   ```

   to

   ```yaml
         packages: [scaleft-server-tools]     # what the base bake installs for `identity_types: [okta]`
   ```

   Leave the `commands:` test under it as it is.

3. Validate, regenerate, commit, and let CI look on `develop`:

   ```sh
   aws sts get-caller-identity                # keys live?
   just validate
   just dry
   grep -n 'is not installed' generated/base-image/packer-ebs/image-generation/block-000/*-build.pkr.hcl   # one line, and it names scaleft-server-tools, not git
   git add -A && git commit -m "The base image's test names a package the base carries"
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch develop --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   ```

   Go on only if it prints `success`.

   (2026-10-07: `just validate` stopped here with `Error reading
   config file : AWS Error: An error occurred (RequestExpired) when
   calling the DescribeVpcs operation: Request has expired` under a
   long traceback. That is expired access keys, not the tree and not
   your edit: the keys in `~/.aws/credentials` were an hour and
   twenty minutes old. Refresh them the way stage 3 says, see
   `aws sts get-caller-identity` answer, and start this step again
   at `just validate`. Finding F30.)

4. The second `perform`. `main` exists now, so this push is an
   ordinary fast-forward:

   ```sh
   git push origin develop:main
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   ```

   The base bake got as far as its tests in about five minutes last
   time; past them it images the machine, and then the bake of
   `team-node` starts. Claude watches the same run from the host and
   reads its log, so if it ends red you need paste nothing: say `red`
   and stop. Do not re-run it.

5. Only after a green run, `develop` takes the records again:

   ```sh
   git fetch origin
   git log --oneline -4 origin/main           # the closing record, the performing run, the first record, then your commit
   git merge --ff-only origin/main
   git push
   grep -E 'build_id:|series:' meta-state/lineage.yaml   # two builds, each its ami id: series el10 and series team-node
   just state-query --strict
   ```

**Report:** `stage 11 done` with what the two `gh run view` lines
printed, the first three lines of the `git log`, and the last line
of the state query; or `red`.

**What happened at 11c (2026-10-07): steps 1-3 worked, and the
second `perform` ended red, again the system's fault** (finding
F29). Run 37652881489 on `main`. The base image's bake got through
its update, made the admin user, and then its third step, the one
that installs the OPA agent, stopped at its first package command:
`error: can't create transaction lock on
/usr/lib/sysimage/rpm/.rpm.lock (Resource temporarily unavailable)`.
Packer stopped after 3 minutes 37 seconds and removed everything;
AWS shows no machine and no image left. The closing record was
pushed: `main` is again two record commits ahead of `develop`. Your
edit was right, and the run never reached the test it changed.

Who held the lock: this AWS account. Its Systems Manager has
"Quick Setup" associations that target EVERY instance: two that
update the session agent, one that scans for patches, one that takes
inventory. On both build machines they fired within forty seconds of
boot (AWS's own record shows them, on each machine, at the second),
which is while packer is provisioning, and they use the package
database the bake is using. `rpm` waits for a busy database only
when a person is at a terminal; in a bake it gives up at once. The
first `perform` met the same collision in its update step and passed
it only because that one step tries twice.

The steps of a bake are written by the system, not by your tree, so
there is nothing here for you to edit. By your decision (2026-10-07,
"Fix now, starters too") the fix is being made now: stage 86. A bake
will first wait for the machine's own first-boot work and the
account's fleet management to finish, and every package step will
wait out a busy database instead of failing. The starters' base test
(F28) is corrected in the same release, 0.1.1.dev18. When it is
merged, a box 11d appears here: you cut the release on your local
machine, the walk takes it, and the third `perform` follows.

**What happened at 11d's first attempt (2026-10-07).** Two slips,
neither of which the tools caught, and nothing was lost:

- Release 0.1.1.dev18 was cut while the system repository's checkout
  was on `feature/walk-daily-driver`, not on `develop` (finding F31:
  the release recipe does not look at the branch). The packages on the
  index are sound, their code is exactly `develop`'s, but the bump
  landed on the walk branch and `develop` still said dev17. By your
  decision the release is cut again, properly, as 0.1.1.dev19 from
  `develop`; dev18 stays on the index, unused, and Claude has reverted
  the bump on the walk branch.
- Step 2, a container box, was typed into the local terminal, which
  stood in the system repository. `cs-image-system init-config .
  --force` there replaced the system repository's own `Justfile`,
  `.gitignore` and CI workflow with a configuration repository's and
  wrote three files beside them (finding F32: `init-config --force`
  does not check that it is in a configuration repository). The new
  `.gitignore` no longer ignored `_uncommitted/`; nothing had been
  staged or committed. Claude copied the six files aside, restored
  the three, moved the three strays out, and the checkout is clean.
  The same box installed 0.1.1.dev18 as a `uv` tool on your local
  machine; step 1 below removes it.

**11d. Release 0.1.1.dev19 from `develop`, take it, the third
`perform`.** Stage 86 is merged. What it changes in a bake, so you
know what you are looking at: every bake now begins with a step that
waits for the build machine to settle (its first-boot script, and on
AWS Systems Manager going quiet: about half a minute on a calm
machine, ten minutes at the very most), and every package step waits
out a busy package database instead of failing on it. No image's
fingerprint changes, so nothing that stands needs to bake again.

1. **On your local machine (the host, NOT the container): cut
   release 0.1.1.dev19 from `develop`.** The version is named,
   because `develop` still says dev17 and `dev` would ask for dev18,
   which the index already holds. Line by line; each of the three
   guarded lines prints `OK` or `STOP`:

   ```sh
   cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3 2>/dev/null && [ -d packages/base ] && echo "OK: local machine, the system repository, $(pwd)" || echo "STOP: this is the container, or the path is wrong"
   uv tool uninstall cs-image-system          # the stray dev18 tool of the first attempt; "not installed" is fine too
   git status --short                         # nothing listed
   git checkout develop && git pull
   [ "$(git branch --show-current)" = develop ] && echo "OK: on develop, at: $(git log --oneline -1)" || echo "STOP: not on develop"
   ```

   The second `OK` line must end with the stage 86 squash, `A bake
   waits for the package database (stage 86)`. Then:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' https://test.pypi.org/legacy/   # 200: the index can take an upload
   [ "$(git branch --show-current)" = develop ] && just release 0.1.1.dev19 test yes || echo "STOP: not on develop"   # dry: 0.1.1.dev17 would become 0.1.1.dev19
   [ "$(git branch --show-current)" = develop ] && just release 0.1.1.dev19 test || echo "STOP: not on develop"       # the bar (about 25 minutes), the upload, the commit, the tag
   git log --oneline -1                       # release 0.1.1.dev19
   git push --follow-tags
   git checkout feature/walk-daily-driver     # brings this document back
   ```

   While you are on `develop` this document is not in the working
   tree; that is expected. Keep it open in the editor, or read the
   lines before you switch.

   **Report:** `dev19 pushed`. Claude confirms the release on the
   index and that it is on `develop` this time, takes it into the
   reference configuration, then says go for step 2.

   (DONE 2026-10-07: release commit 1ad6978 is on `develop` with the
   tag `v0.1.1.dev19`; 18 of 18 packages are on the index. Go for
   step 2. The reference configuration takes the release separately
   and nothing in steps 2 to 4 waits for it.)

2. **In the container: the walk takes the release.** The release is
   out (see above). Open the container the way stage
   1 does (`docker exec -it -u mykel.alvis csis-walk bash -l`, from
   your local terminal); its prompt reads `[mykel.alvis@csis-walk
   ...]$`. `develop` first takes the two records the second failed
   run pushed to `main`:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status -sb                             # develop...origin/develop, nothing listed
   git fetch origin
   git merge --ff-only origin/main            # Fast-forward: two record commits
   uv tool install --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ "cs-image-system==0.1.1.dev19"
   uv tool list                               # cs-image-system v0.1.1.dev19
   [ "$(pwd)" = /walk/cs-image-system-walk ] && [ -f cfg/_config.yml ] && cs-image-system init-config . --force || echo "STOP: not the walk tree in the container"
   cat .csis-version                          # 0.1.1.dev19
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just validate
   just dry
   grep -c 'the build machine settles' generated/base-image/packer-ebs/image-generation/block-000/*-build.pkr.hcl generated/instance-image/packer-ebs/image-generation/block-000/*-build.pkr.hcl   # 1 and 1: each bake begins with the settle
   git add -A && git commit -m "Take release 0.1.1.dev19: a bake waits for the package database"
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch develop --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   ```

   Your own edit to `cfg/os-builders.yml` stays: `cfg/` is yours,
   and `init-config` does not rewrite it. If `init-config` names any
   file other than `.csis-version`, say which. Go on only if the
   last line prints `success`.

3. **The third `perform`**, in the container:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git push origin develop:main
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   gh run view "$run" --json conclusion,jobs --jq '.conclusion, (.jobs[] | "\(.name): \(.conclusion)")'
   ```

   Claude watches the same run from the host and reads its log. If
   it ends red, say `red` and stop; do not re-run it.

4. Only after a green run, `develop` takes the records, in the
   container:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git fetch origin
   git log --oneline -4 origin/main           # the closing record, the performing run, the first record, then your commit
   git merge --ff-only origin/main
   git push
   grep -E 'build_id:|series:' meta-state/lineage.yaml   # two builds, each its ami id: series el10 and series team-node
   just state-query --strict
   ```

**Report:** `stage 11 done` with what the two `gh run view` lines
printed, the first three lines of the `git log`, and the last line
of the state query; or `red`.

The fifth proof of 3.8, the login proof AS the workload and then the
branch pin on the role, needs a machine to log into: it is in stage
12, after the launch.

## Stage 12 onward -- written when you reach them

These stages depend on what the earlier ones produce (the bootstrap's
interview, the names it prints), so their exact commands are added to
this page as each one comes up. The order, and the page each follows:

| Stage | What | Follows |
| --- | --- | --- |
| 12 | Making things, the rest: the images `perform` baked read back, the durable machine launched, the group on it, the login proof by hand and then as the workload, the branch pin on the role | DAILY_DRIVER 3.3-3.5; CI_SETUP 3.8 step 5 |
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
| F22 | the system cannot create a NEW group in OPA: the identity root looks the group's gid up at plan time, before the group exists, and the creating plan fails | code: stage 84 |
| F23 | the guide (3.5 step 4) and the probe workflow's header say a DRAFT connection "validates the token and issues nothing usable"; run against a draft, the probe's own success line says the connection "accepted this run's token and issued one" | words |
| F24 | the first identity apply of a new tree stops at the prune step: a root with no state yet makes `tofu state list` fail ("No state file was found"), and the step treats that as an error | code: stage 85, released in 0.1.1.dev17 |
| F26 | PREDICTED, not run (the operator chose to apply the storage first): the first `perform` of a tree made from the starter fails after its bakes. The instance root reads its storage root's state, a performing run plans the instance root, and the guide's order (CI_SETUP 3.8 step 4 before the daily driver's section 3) reaches `perform` before any storage run, so the plan stops with `Unable to find remote state`. Reproduced on a scratch root; the walk's bucket held no storage state | code and words: hygiene XII item 9 |
| F27 | CI_SETUP 3.2 and 3.8 say "merge `develop` into `main`"; a repository made from nothing has no `main` on GitHub (the bootstrap sets the default branch and the ruleset, it does not create the branch), so the first `perform` is a push that creates it; and the branch the repository was created with (`master` here) stays behind, unused and unmentioned | words |
| F28 | the starters `standard-aws`, `standard-aws-posix` and `standard-gce` test their BASE image for the package `git`, which nothing installs on a base (the vendor's AlmaLinux 10 image has none; a base takes no modifications; git comes from the image's playbook). The first base bake of a tree made from them fails its own test after five minutes: `package git is not installed`. Seen in the walk's first `perform` | starter: stage 86, released in 0.1.1.dev19 (was hygiene XII item 10) |
| F29 | a bake's package steps race the AWS account's own fleet management. Systems Manager "Quick Setup" associations that target every instance (agent update, patch scan, inventory) fire on a build machine within forty seconds of boot and hold the package database; `rpm` does not wait for it without a terminal. The walk's first `perform` survived it once (the update step alone retries); the second failed on it: `can't create transaction lock on /usr/lib/sysimage/rpm/.rpm.lock` | code: stage 86, released in 0.1.1.dev19 (was hygiene XII item 11) |
| F30 | expired access keys reach the operator as `Error reading config file : AWS Error: ... (RequestExpired) ... Request has expired` under a hundred-line traceback: the words blame the configuration, and the daily driver's failure table (section 6, the expired-session row) shows `Token has expired` and `a session has EXPIRED` but not `RequestExpired`, which is what temporary keys in the environment or a credentials file produce | words (and the traceback: hygiene XII, with stage 6's) |
| F31 | `just release` cuts from whatever branch is checked out: 0.1.1.dev18 was cut on the walk branch, its bump and tag landed there, and `develop` was left a version behind. The recipe probes the token, the index, the version and a clean tree, and never the branch | code: stage 83 (the release's probes) |
| F32 | `cs-image-system init-config . --force` does not check that it stands in a configuration repository: run in the system repository's root it replaced that repository's `Justfile`, `.gitignore` and CI workflow with a starter's and wrote `.csis-version`, `CI_SETUP.md` and the probe workflow beside them; the new `.gitignore` stopped ignoring the checkout's private directory. It guessed a starter from a workflow file and asked nothing | code: hygiene XII item 12 |
| F25 | an applying run's log can lose the one line that says what was applied: it keeps the last 40 lines of a command's output, and tofu prints `Apply complete! Resources: ...` BEFORE the root's outputs, so a root with 37 or more lines of outputs (the reference's identity root: 40) shows only outputs | code: hygiene XII item 8 |
