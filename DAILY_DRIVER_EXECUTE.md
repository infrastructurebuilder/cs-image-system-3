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

**A check ends its box.** (Your rule, 2026-10-09.) Where a command's
output has to be looked at before going on, that command is the
LAST line of its box, and the words straight under the box say what
it must show and when to STOP. Nothing that acts comes after a
check inside the same box, because a box is pasted whole: a `git
status` that had to be read, with `just record` on the line after
it, has recorded before anyone has read it. (That happened at 14g
on 2026-10-09; the record was cancelled with Ctrl-C.) So a step
with a gate in it is several boxes, each ending on what must be
read. Boxes written before that day are not all built this way;
every box from the end of 14g on is.

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
| 11d, step 2 (the walk takes 0.1.1.dev19) | done 2026-10-07: commit 4e735f1, CI green |
| 11d, step 3 (the third `perform`) | done 2026-10-07: GREEN. Both images baked; nothing left behind |
| 11d, step 4 (`develop` takes the records) | done 2026-10-08: `develop` and `main` are level |

**Stage 11 is DONE (2026-10-08).** Every box below is the record of
what happened; your next command is in stage 12.

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

**What happened at 11d's steps 2 and 3 (2026-10-07): it worked.**
Run 37702632991 on `main`: `verify`, `live` and `perform` all green.

- The base image `el10` baked in 10 minutes 2 seconds:
  `ami-0f3c5c4c637ccff19`, ten in-bake assertions passed. The image
  `team-node` baked from it in 5 minutes 56 seconds:
  `ami-03a8cef5e12cd1b50`, its two modifications applied, seven
  assertions passed. AWS shows both `available` and tagged for this
  configuration; `meta-state/lineage.yaml` on `main` records both.
- No step met a held package database: the words `transaction lock`
  are nowhere in the run. AWS's own record says why. Systems Manager
  fired on both build machines again, about half a minute after
  launch, and this time its patch scan and its agent update ended
  `Success` on both, where they had ended `Failed` on the two earlier
  runs' machines: the bake stood aside until they were done.
- What the log does NOT show is the settle step saying so. The log
  keeps the last 40 lines of a command that succeeds (`packer build
  stdout (last 40 of 304 lines; all at DEBUG)`), and the settle is the
  first thing a bake prints: finding F25 again, for bakes.
- The instance root planned `3 to add, 0 to change, 0 to destroy`,
  passed the gate and was NOT applied (`apply_instances` is `false`).
- `CI logs in through the managed policy` minted an OPA token as the
  workload, from `main`, for the first time (`sft workload
  authenticate exit 0; stdout carried a token`), and found `no
  standing instance to log into`: nothing to prove yet.
- The strict state query said `no drift: meta-state agrees with
  reality`. `perform` pushed its three records; `main` is three
  commits ahead of `develop` until step 4.

Stage 86 is proved by the run it was written for, and with it the
WRITE role the bootstrap made: it launched, reached, imaged and
removed two build machines.

The fifth proof of 3.8, the login proof AS the workload and then the
branch pin on the role, needs a machine to log into: it is in stage
12, after the launch.

## Stage 12 -- the machine: launch, verify, the group on it, the login proof (DAILY_DRIVER 3.5, 3.1; CI_SETUP 3.8 step 5)

Read the daily driver's 3.5 and, in 3.1, "The group on its machines".
Of section 3, the group (stage 10), the storage (11a) and both images
(the third `perform`) exist. What is left is the instance
`walk-node-1`: one t3.medium machine that STANDS until teardown
(stage 17), built from `team-node`, with the volume `data` at
`/mnt/data`. This is the first machine the walk owns.

The records already say what the launch will make of it
(`meta-state/launch-params.yaml`): hostname `walk-node-1-001`, the
first generation of that name; build `ami-03a8cef5e12cd1b50`;
enrolled in OPA with the project's token under the label
`sftd.tx.group=walk_team`; the volume on `/dev/xvdf`, mounted at
`/mnt/data` with the group's subtree `2770`.

| Part | State |
| --- | --- |
| 12a, step 1 (the dry form) | done 2026-10-08: the script ends with plan, gate, apply-check and apply; nothing launched |
| 12a, steps 2-3 (the launch, its records, CI) | done 2026-10-08: the machine stands; CI green; no drift |
| 12b. Verify the machine | done 2026-10-08: `instance walk-node-1 verified` |
| 12c, steps 1-3 (the `sft` client, the group on the machine, the proof by hand) | done 2026-10-08: `login proved for walk-node-1` |
| 12c, step 4 (the record, the push, CI) | done 2026-10-08: both verdicts committed (483385c), CI green |
| 12d. The login proof as the workload | done 2026-10-08: GREEN; `as: workload` is on `main` |
| 12e, steps 1-2 (the pin in the console; the bootstrap sees it) | done 2026-10-08: the role reads back from OPA with `ref` Equals `refs/heads/main` |
| 12e, step 3 (the probe from both sides) | superseded: the probe cannot see the pin (F35) |
| 12e, steps 4-6 (the pin proved from both sides; the throwaway branch removed) | done 2026-10-08: `main` gets in, another branch is refused |

**Stage 12 is DONE (2026-10-08).** Every box below is the record of
what happened; your next command is in stage 13.

One line you will keep seeing until the machine exists, from every
state query and from the launch's own preflight:

```
unavailable: instances/walk-node-1: booted image (runtime aws-main could not answer)
```

It is not a failure and stops nothing (the strict query passes on
it). The bake pinned `walk-node-1` to its image, the query asks AWS
which image the machine booted, and there is no machine yet; the
words blame the cloud for a machine that was simply never launched.
Finding F33.

**12a. The launch.** In the container. `just cloud-launch` is the
instance-image lifecycle with nothing baking and this runtime's roots
allowed to apply for this one run; `apply_instances` stays `false` in
`cfg/_config.yml`, and you edit nothing.

1. The dry form first, and read what it would run:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status -sb                             # develop...origin/develop, nothing listed
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just cloud-launch aws-main yes
   tail -4 generated/instance-image/run-instance-image.sh
   ```

   The script's last lines should be the instance root's `tofu plan`,
   `gate-plan`, `apply-check` and `tofu apply`. A dry launch plans
   nothing against AWS and launches nothing. It does commit its own
   record (`cs-image-system dry-run generation ...: instance-image`),
   so `develop` is one commit ahead of GitHub until step 3 pushes.

   (DONE 2026-10-08: exactly that. The dry form is not the launch:
   AWS has no machine yet and the records still say `launched:
   false`. Step 2 is the launch.)

2. The launch:

   ```sh
   just cloud-launch aws-main 2>&1 | tee ~/launch-12a.log
   ```

   The `tee` keeps the whole output in your home directory in the
   container (not in the repository), because Claude cannot see your
   screen and this run says several things worth reading afterwards.
   What should happen, in order; Claude has not seen a launch in this
   tree, so the exact lines are not promised:

   - the preflight (a strict state query), with the `unavailable`
     line above;
   - the instance root's plan, `3 to add, 0 to change, 0 to destroy`
     (the machine, its security group, the volume's attachment), the
     gate's verdict, the apply;
   - after the apply, work ON the machine through Session Manager,
     which needs it running and its agent answering: its other names
     (lines beginning `Instance walk-node-1:`) and the group
     `walk_team` made on it. If the machine is not ready in time,
     those lines say so and the next launch run does them: that is
     not a failure;
   - `Run ... completed: instance-image` and a meta-state commit.

   If the run fails, STOP and paste the last thirty lines (`tail -30
   ~/launch-12a.log`). Do not run it again: a half-made machine is
   something to look at first.

3. Record it and let CI look:

   ```sh
   git status --short                         # nothing listed: the run committed its records
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
   just state-query --strict
   grep -nE 'Plan:|Apply complete|Instance walk-node-1|walk_team|alias|WARNING|ERROR|completed:' ~/launch-12a.log | cut -c1-200
   ```

   If `git status --short` lists anything, paste it before you push.

**Report:** `stage 12a done` with what the last `grep` printed, what
the `gh run view` line printed, and the state query's lines; or the
error. STOP there: Claude reads the machine from AWS and the records,
and writes 12b and 12c with the names the launch really gave it.

**What happened at 12a (2026-10-08): it worked, first time.** `Plan:
3 to add, 0 to change, 0 to destroy`, `Apply complete! Resources: 3
added`, and then, on the machine itself through Session Manager:
`Instance walk-node-1: now also answers to ['walk-node-1',
'ip-10-26-35-48'] (sftd restarted)` and `Instance walk-node-1: the
accounts of group walk_team are in place`. `Run
2026_10_08t00_40_35_658425 completed: instance-image`, committed as
c2ce743 and pushed; CI green; the strict state query says `no drift`
and the `unavailable` line is gone, as it should be now that there
is a machine to ask.

What AWS says of it, read by Claude: instance `i-03903ef85cecb0dc2`,
`running`, a t3.medium in us-east-2a on the image
`ami-03a8cef5e12cd1b50` (the pinned build of `team-node`), private
address 10.26.35.48 and NO public address, the session profile
attached, and the volume `data` on `/dev/xvdf`. The records agree:
`meta-state/instance-state.yaml` opened generation 1 of
`walk-node-1` with that instance id, `observed`.

Three names reach it: its hostname `walk-node-1-001`, and the two
the launch added, `walk-node-1` and `ip-10-26-35-48`.

**12b. Verify the machine.** In the container. The system asks the
machine itself, through Session Manager: did its startup script run
to its end, is it on the image its pin names, are its mounts there.
The verdict is recorded in `meta-state/verifications.yaml`.

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
just cloud-verify aws-main walk-node-1 2>&1 | tee ~/verify-12b.log | tail -30
```

It prints the record as JSON, one entry per check (`startup
scripts`, `booted image`, the mounts), and ends `instance walk-node-1
verified`. If it ends any other way, STOP and paste what the `tail`
showed; do not go on to 12c.

**12c. The `sft` client, the group on the machine, the login proof
by hand.** In the container, straight after a `verified`.

OPA lets a PERSON in through a client that is enrolled for them. Your
local machine's client is enrolled; the container's never was, and
the walk's tools live in the container, so this one is enrolled now.
Enrollment and login each want a browser, which the container does
not have: the client should print a link instead. Open it in the
browser of your local machine, where you are signed in to Okta, and
approve. Do NOT paste the link into the chat: it authorises a client
as you. Whether this works from a container at all is what stage 7
left to find out; if the client does anything but print a link,
paste its words (never a link) and stop.

1. Enroll and log in:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   sft enroll --url https://noaa.pam.okta.com --team nos-coastal-modeling-cloud-sandbox
   sft login
   sft list-teams                             # your user, the team, STATUS a time remaining, not "Expired"
   sft resolve walk-node-1                    # one server: the machine of 12a
   ```

2. The group on its machine (the daily driver's 3.1). The first
   login is also what makes your account on the machine:

   ```sh
   sft ssh walk-node-1 --command 'hostname; id; getent group walk_team; ls -ldn /mnt/data/walk_team; ls -ld /mnt/data/walk_team; df -h /mnt/data | tail -1'
   ```

   What the page promises, line by line: the hostname
   `walk-node-1-001`; an `id` whose groups include `walk_team`; a
   `getent` line for `walk_team` with a number (OPA's gid) and you as
   a member; the group's subtree owned by that same number and shown
   by NAME in the second listing, mode `drwxrws---`; and a filesystem
   of about 100G on `/mnt/data`.

   If `id` does NOT list `walk_team` this first time, run the very
   same line once more and report both outputs: a member is added to
   the group when they log in, and whether the FIRST login already
   carries it is something the page does not say.

3. The login proof by hand. The same login, made by the system and
   recorded:

   ```sh
   just ci-login-proof walk-node-1 2>&1 | tee ~/proof-12c.log | tail -20
   ```

   It says it is `not a GitHub Actions job -- logging in as the
   enrolled client, not the workload`, logs in, and records the
   verdict in `meta-state/login-proofs.yaml`.

4. Record both verdicts and let CI look. Neither command commits, so
   the record does (a dry run of every lifecycle, committed):

   ```sh
   git status --short                         # meta-state/verifications.yaml and meta-state/login-proofs.yaml, modified or new
   just record
   git status --short                         # nothing listed
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

   If the second `git status --short` still lists a file, paste it
   before you push.

**Report:** `stage 12c done` with the last line of the verify, what
the `sft ssh` line printed (all of it: it holds no secret), the last
five lines of the proof, and what the `gh run view` line printed; or
the words of whatever stopped you. If CI printed `success`, go
straight on to 12d and report both together.

**What happened at 12b and 12c's steps 1-3 (2026-10-08): all of it
worked.** The verify recorded three checks, all `ok`: the startup
script ran to its end, the machine booted the image its pin names,
its one declared mount is there. Enrolling the `sft` client from a
container, the question stage 7 left open, works: each command prints
a link, and both opened on your local machine. The first login showed
every line the daily driver's 3.1 promises, at once:
`walk-node-1-001`; an `id` with `180049(walk_team)`; `walk_team:x:
180049:mykel.alvis`; the group's subtree owned by 180049, named
`walk_team`, mode `drwxrws---`; 100G at `/mnt/data`. And the system's
own proof: `logged in as mykel.alvis over sft ssh`, `login proved for
walk-node-1`.

**12d. The login proof as the workload.** In the container. CI makes
the same login you just made, with no key and no person: the
`perform` job on `main` presents GitHub's token for this run to the
connection of 10a, becomes the role of 10b, and logs in through
`walk_team_v1_security_policy_ci`, the policy the identity run of
10c made for it. Nothing is due to bake, so this run is short.

1. Start it and watch:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
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

   In `perform`, the step to look at is `CI logs in through the
   managed policy`. Claude watches the same run from the host and
   reads its log. If it ends red, say `red` and stop; do not re-run
   it.

2. Only after a green run, `develop` takes the records, and the
   proof is read back:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git fetch origin
   git merge --ff-only origin/main
   git push
   grep -nE '^- as:|^  (instance|ok|time):' meta-state/login-proofs.yaml
   ```

   Two entries, four lines each. The first is yours of 12c: `- as:
   client`. The second is CI's: `- as: workload`, `instance:
   walk-node-1`, `ok: true`.

**Report:** `stage 12d done` with what the `gh run view` line printed
and what the `grep` printed; or `red`. Then STOP: Claude confirms the
proof on `main` before the role is pinned to it.

**What happened at 12d (2026-10-08): it worked, and Claude confirms
the proof on `main`.** Run 37711188808: `verify`, `live` and
`perform` green, in about two minutes of performing. Nothing baked
(both images `skip: current`); the instance root's plan said `No
changes. Your infrastructure matches the configuration`, which is
the first time a plan has looked at the standing machine and found
it as declared. Then `CI logs in through the managed policy`:
`workload token: sft workload authenticate exit 0`, and `logged in
as wl_cs_image_system_walk_ci over sft ssh`, `login proved for
walk-node-1`.

`meta-state/login-proofs.yaml` on `main` now holds two entries for
`walk-node-1`. Yours, `as: client`: `uid=150006(mykel.alvis)` with
the groups `sft-admin` and `walk_team`. CI's, `as: workload`:
`uid=150034(wl_cs_image_system_walk_ci)` with no group but its own.
That difference is the design showing: the CI policy lets the
workload in and gives it nothing, no sudo and no place in the team's
group. It is the fifth and last proof of the CI guide's 3.8.

**12e. The branch pin on the workload role.** 12d is confirmed
(CI_SETUP 3.5 step 6: "after the first green login proof from
`main`"). Until now any branch of this repository could become the
role; from here only `main` can.

1. You, in the OPA console (it needs the security-admin role). The
   pin goes in ONE place, the ROLE: Security Administration, Workload
   roles, `cs-image-system-walk-ci`. The role lists the connection it
   is bound to, `github-cs-image-system-walk`; in the role's entry
   for that connection, add the condition `ref` Equals
   `refs/heads/main`, and save.

   Do NOT touch the connection itself (DevOps Administration,
   Workload connections): its Required Claims stay `repository` and
   `repository_owner` and it gets no `ref` claim, as 10a said. The
   connection answers "is this token from this repository?"; the
   role answers "and from which branch may it become me?". The
   bootstrap looks for the pin in the role and nowhere else, so a
   `ref` claim put on the connection would be read as "not pinned",
   and it would also turn away the probe from every other branch
   before it could say why.

   (This step first read "on the role ..., and on the connection
   ...", which sounded like two places. It is one.)

2. In the container, let the bootstrap see it. This asks the Okta
   and OPA section alone; Enter at every question. The one answer
   that should have changed is the last of the role's: `Is the role
   pinned to the production branch ...?` now offers `[Y/n]`. If it
   still shows `[y/N]`, press Ctrl-C and say so.

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   just bootstrap --section okta
   git status --short                         # expect two lines: M bootstrap.yaml and M generated/bootstrap/README.md
   grep -n -A3 '^- \*\*okta\*\*' generated/bootstrap/README.md   # the role's line now ends: pinned to `main`: yes
   git add -A && git commit -m "The workload role is pinned to main"
   git push
   ```

3. (SUPERSEDED 2026-10-08: this step asked the probe to show the
   pin, `main` let in and `develop` kept out. It cannot. Both probes
   said `success`, and both were right: see "What happened" below.
   Steps 4 to 6 are the proof.)

**What happened at 12e's steps 1-3 (2026-10-08).** The pin is set
correctly: Claude read the role back from OPA, and it holds one
requirement, the connection `github-cs-image-system-walk`, with the
one condition `ref` Equals `refs/heads/main`; the connection keeps
its two claims and no `ref`. The bootstrap saw the same (`pinned to
`main`: yes`), committed as 41daa01.

Then the probe ran on `main` and on `develop`, and said `success`
both times: `the connection accepted this run's token and issued
one`. Claude had written that a success on `develop` would mean the
pin was not holding. That was wrong, and it was Claude's invention,
not the guide's. The probe authenticates to the CONNECTION, which
asks only whether a token is this repository's; the role is passed
to the client as a hint ("the desired role the workload will assume,
if authorized"), and being issued a token says nothing about having
been given the role. So the probe cannot see the pin at all, from
either side (finding F35). What is still unproven is the thing that
matters: that a workload from another branch is REFUSED. By your
decision ("Prove it now") the next three steps show it with a real
login attempt.

4. The pin must not have locked `main` out. `develop` holds the
   bootstrap's commit of step 2, which `main` does not have yet, so
   pushing it makes one more `perform`, and its login is the first
   made as the workload WITH the pin in place. In the container:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status -sb                             # develop...origin/develop, not ahead; one untracked file: .github/workflows/pin-proof.yml
   git push origin develop:main
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "perform on main, pinned: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
   git fetch origin && git merge --ff-only origin/main && git push
   grep -c '^- as: workload' meta-state/login-proofs.yaml    # 2: the proof before the pin, and this one after it
   ```

   The untracked file is the temporary workflow Claude wrote into
   the tree for step 5; leave it where it is and do NOT `git add`
   it here. If the run is not `success`, STOP and say `red`: a pin
   that locks `main` out is to be taken off before anything else.

5. The refusal. A throwaway branch, `pin-proof`, carries one extra
   file, `.github/workflows/pin-proof.yml`: on a push to that branch
   it makes the very login `perform` makes on `main`, `just
   ci-login-proof` as the workload, from a ref that is not `main`.
   Its job is GREEN when OPA issues the connection's token and then
   REFUSES the login (the pin holds), and RED when the login succeeds
   (the pin does not hold) or the attempt could not be judged. Read
   the file first if you like; nothing in it writes anywhere.

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status --short                         # exactly one line: ?? .github/workflows/pin-proof.yml
   git checkout -b pin-proof
   git add .github/workflows/pin-proof.yml && git commit -m "TEMPORARY: prove the workload role's branch pin (never for main)"
   git push -u origin pin-proof
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch pin-proof --commit "$(git rev-parse HEAD)" --json databaseId,workflowName --jq '[.[] | select(.workflowName == "TEMPORARY pin proof")][0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "pin proof: $(gh run view "$run" --json conclusion --jq .conclusion)"
   gh run view "$run" --log | grep -E 'this run.s ref:|PIN HOLDS|PIN DOES NOT HOLD|INCONCLUSIVE|login proof FAILED|ci-login-proof exit' | cut -d$'\t' -f3- | cut -c30-260
   git checkout develop
   git status -sb                             # develop...origin/develop, nothing listed
   ```

   The push also starts the ordinary `CI` workflow on that branch
   (`verify` and `live`); it is not the run these lines watch (they
   pick the run named `TEMPORARY pin proof`), and its result does not
   matter here. The temporary workflow uses the READ-ONLY AWS role,
   which trusts every branch of this repository; the WRITE role
   trusts `main` alone and is not touched. Expected: `pin proof: success`
   and a line `PIN HOLDS: OPA issued the connection's token to
   refs/heads/pin-proof and then refused the login`. If it prints
   `PIN DOES NOT HOLD`, say so at once. Either way, do not go on to
   step 6 until Claude has read the run.

6. Remove the throwaway branch. Only after Claude says the run is
   read. It never reached `develop` or `main`:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   [ "$(git branch --show-current)" = develop ] && git push origin --delete pin-proof && git branch -D pin-proof || echo "STOP: not on develop"
   git branch -a | grep -c pin-proof          # 0
   ls .github/workflows/                      # ci.yml and opa-workload-probe.yml: the temporary file went with its branch
   ```

**Report:** `stage 12 done` with the `perform on main, pinned:` line,
the `pin proof:` line and the lines the last `grep` of step 5 printed.

**What happened at 12e's steps 4-6 (2026-10-08): the pin holds, and
it is proved from both sides.**

- From `main`, with the pin in place: run 37759023233 at 41daa01,
  `perform` green. `meta-state/login-proofs.yaml` on `main` gained a
  third entry, `as: workload`, `logged in as
  wl_cs_image_system_walk_ci over sft ssh`, at 09:51:29Z. The pin did
  not lock `main` out.
- From another branch: run 37760563336, `TEMPORARY pin proof` on
  `refs/heads/pin-proof`. OPA issued the connection's token
  (`workload token: sft workload authenticate exit 0`), exactly as it
  had for the probe; and then the workload could not so much as find
  the machine: `sft resolve walk-node-1-001: exit 125`, `login proof
  FAILED for walk-node-1`. The job's verdict: `PIN HOLDS: OPA issued
  the connection's token to refs/heads/pin-proof and then refused the
  login`.

So a token from any branch of this repository is accepted by the
connection, and only one from `main` is given the role. The
throwaway branch is gone from GitHub and from the container, and the
temporary workflow with it; `develop` and `main` are level.

## Stage 13 -- changing things: a modification, then a member (DAILY_DRIVER 4)

Read the daily driver's section 4: its first row ("A modification, a
test or a package on an image") and its two membership rows ("Who
may log in", "Who is in a group on its machines").

| Part | State |
| --- | --- |
| 13a. A modification: re-bake, and the machine takes the new build | done 2026-10-08: baked from the container, the machine replaced, its data intact, `perform` green |
| 13b, steps 1-5 (the second person declared, OPA and the machine told, their login) | done 2026-10-08, and it found a defect: they logged in and did NOT join the group (finding F37) |
| the fix for F37 (stage 87) | merged 2026-10-08; it needs release 0.1.1.dev20 |
| 13b again, step 1 (release 0.1.1.dev20 from `develop`) | done 2026-10-08: cut on `develop`, tagged there, all 18 packages on the index |
| 13b again, steps 2-3b (the walk on 0.1.1.dev20, the list rewritten, the second person's login) | done 2026-10-08: their own session carries `walk_team`. Stage 87 is proved |
| 13b again, step 4 (record, push, CI) | done 2026-10-08: 2a99d31, CI green |
| 13c, steps 1-2 (the edits undone; the identity run) | done 2026-10-08: the gate REFUSED the run, by design, and nothing changed (finding F38) |
| 13c, step 2b, first half (the person removed in the OPA console) | done 2026-10-08 |
| the fix for F38 (stage 88) | merged 2026-10-08 (20206e8); it needs release 0.1.1.dev21 |
| 13c, step 2b, second half (the container: the identity run again) | done 2026-10-08: the prune step took the attachment out of state, the runner's plan said `No changes`, the run completed (3ce4cc6) |
| 13c, steps 3 and 4 (the launch run and the count; record, push, `main`) | done 2026-10-08: the launch run completed (c3cbaad); `perform` on `main` green at b1cce04, its login proof `ok`, no drift. The second person's refusal: not tried |
| 13d, step 1 (your local machine: release 0.1.1.dev21 from `develop`) | done 2026-10-08: release commit 40f3efc on `develop`, tag `v0.1.1.dev21`, 18 of 18 packages on the index; the reference configuration has taken it |
| 13d, steps 2-5 (the walk on 0.1.1.dev21: the second person back in, and out again by the YAML alone) | done 2026-10-09 (00:56 UTC): they went in by a run and came out by a run; the gate sanctioned exactly their attachment; OPA's console and its API both say `walk_team_user` has no members. **Stage 88 is proved** |
| 13d, step 6 (record, push, `main`) | done 2026-10-09: `perform` on `main` green at 753bb65, on 0.1.1.dev21. **Stage 13 is done; stage 14 is next** |

For 13b you chose to add a second person. While 13a runs, settle who:
a real Okta account in the same team, whose owner agrees to be a
member of `walk_team` for a day. You will need their OPA username
(as you needed your own in stage 6) and to know whether their Okta
login has the same mail domain as yours. Do not put either in the
chat; say only `second person ready`, and whether the domain is the
same.

**13a. A modification.** In the container. The image `team-node`
gets a second line in its configuration file and a test that reads
it. That changes the image's inputs, so a new build is due; this
time the bake is made from the container, with your keys, which is
the daily driver's own way (`just cloud-perform`) and the first bake
of the walk that is not CI's. The standing machine then takes the
new build in one command, which REPLACES it: `walk-node-1-001` goes
and `walk-node-1-002` comes, with the same volume and its data.

1. Leave a mark on the storage, to find again on the new machine:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   sft list-teams                             # STATUS a time remaining; if it says Expired: sft login (a link, as in 12c)
   sft ssh walk-node-1 --command 'echo "planted on $(hostname) at $(date -u +%FT%TZ)" > /mnt/data/walk_team/planted-13a; cat /mnt/data/walk_team/planted-13a'
   ```

   It prints the line it wrote, naming `walk-node-1-001`.

2. The change, in `images/images.yaml`, two places in `team-node`.
   Under `site-files`, the file's content gains a line:

   ```yaml
               content: "role=worker\nwalk=13\n"
   ```

   (it was `"role=worker\n"`). And under `tests:`, `commands:` gains
   a second entry after the `python3` one, at the same indentation:

   ```yaml
           - run: "cat /etc/team-node.conf"
             contains: "walk=13"
   ```

3. Validate, see that a bake is due, commit, and let CI prove the
   modification offline (its `live` job runs every modification twice
   in a container; the walk's container has no docker, so `just
   test-mods` is CI's here):

   ```sh
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just validate
   just dry
   grep -A3 '"bake_plan"' generated/run-summary.json    # el10: skip: current; team-node: bake: inputs changed
   git add -A && git commit -m "team-node: its config file gains a line, and a test reads it"
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch develop --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "CI on develop: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
   ```

   Go on only if it says `success`. Push `develop` only: a push to
   `main` now would have CI make this bake instead of you.

4. The bake, from here. Expect six to ten minutes, most of it
   silence while packer works; the first minute or so is the settle
   step of stage 86 waiting for the build machine:

   ```sh
   aws sts get-caller-identity                # the keys must outlast the bake: refresh them now if they are past half an hour
   just cloud-perform aws-main 2>&1 | tee ~/bake-13a.log
   grep -nE "Build '.*' (finished|errored)|AMI: |csis|Plan:|No changes|completed:|ERROR" ~/bake-13a.log | cut -c1-200
   ```

   What should be among the `grep`'s lines: `Build
   'packer-ebs-block-000.amazon-ebs.team-node' finished after ...`,
   an `AMI:` line, `No changes` for the instance root (the machine
   stays on its pinned build until step 5), and `Run ... completed`.
   Claude has not seen a bake from this container: if it fails, STOP
   and paste `tail -40 ~/bake-13a.log`.

5. The machine takes the build. One command, four runs inside it:
   the pin moves to the new build, a gated launch REPLACES the
   machine, the new one is verified, and a last launch gives it its
   names. Expect eight to fifteen minutes:

   ```sh
   aws sts get-caller-identity                # again: this must not meet an expiry half way
   just cloud-upgrade aws-main walk-node-1 2>&1 | tee ~/upgrade-13a.log
   grep -nE 'Plan:|Apply complete|Instance walk-node-1|verified|completed:|cloud-upgrade:|ERROR' ~/upgrade-13a.log | cut -c1-200
   ```

   If it stops part way, do NOT run it again: paste the `grep`'s
   lines and `tail -30 ~/upgrade-13a.log`. A replacement that stopped
   between its steps is something to read first.

6. Look at the new machine, and prove the login again:

   ```sh
   sft ssh walk-node-1 --command 'hostname; cat /etc/team-node.conf; cat /mnt/data/walk_team/planted-13a; id; getent group walk_team'
   just ci-login-proof walk-node-1 2>&1 | tail -4
   ```

   What the page promises: the hostname `walk-node-1-002`; the two
   lines `role=worker` and `walk=13`; the mark of step 1, still
   naming `walk-node-1-001`; your `id` with `walk_team`; the group.
   If `sft ssh walk-node-1` cannot find the machine, try `sft ssh
   walk-node-1-002` and say which worked.

7. Record it, push, and let `main` see it:

   ```sh
   just record
   git status --short                         # nothing listed
   git push
   git push origin develop:main
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "perform on main: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
   git fetch origin && git merge --ff-only origin/main && git push
   ```

   That `perform` has nothing to bake (your build is recorded) and
   logs in to the NEW machine as the workload.

**Report:** `stage 13a done` with the two `grep` outputs (steps 4 and
5), everything step 6 printed, and the `perform on main:` line; or
the words of whatever stopped you.

**What happened at 13a (2026-10-08): the daily driver's first row of
section 4, end to end, from a person's machine.**

- The bake, from the container with your keys: `Build
  'packer-ebs-block-000.amazon-ebs.team-node' finished after 7
  minutes 11 seconds`, `ami-04bb9df333af05e5b`; the instance root
  said `No changes` because the machine's pin still named the old
  build. No package-lock trouble: stage 86 holds outside CI too.
- The upgrade, about six and a half minutes: `Plan: 2 to add, 0 to
  change, 2 to destroy` (the machine and its volume attachment),
  through the gate; generation 1 closed `replaced`, its OPA
  registration retired; generation 2 is `i-0792ba0408f0e1388`,
  `walk-node-1-002`, with its two other names and the group's
  accounts in place in the same run; verified; `cloud-upgrade:
  walk-node-1 stands on its released build`.
- On the new machine: `walk-node-1-002`; `role=worker` and
  `walk=13`; `planted on walk-node-1-001 at 2026-10-08T10:26:08Z`,
  the mark of a machine that no longer exists; your `id` with the
  same uid and `180049(walk_team)`; `login proved for walk-node-1`.
- On `main`: run 37773784906, `perform` green with nothing to bake
  (the build you made is `skip: current` for CI), the instance plan
  `No changes`, and the workload logged in to `walk-node-1-002`.
  `meta-state/login-proofs.yaml` holds five proofs: three of the
  first machine, two of the second.

**Before 13b: a declared username is public here** (finding F36).
You chose to add a second person. Before anyone is named, know what
declaring them does. `groups/users.yaml` holds a person's `name` as
an `ENC[age:...]` marker, and that suggests the name is private. It
is not. The run writes the same name in clear into what it commits:
`meta-state/identity.yaml` (the `members:` and `admins:` lists), the
identity roots' HCL (`admins = ["..."]`, a resource named after the
person, the local part of their mail address), and, once they log
in, `meta-state/login-proofs.yaml`. This repository is PUBLIC, and
its history keeps what was once committed. Your own username is in
all of those files already. A second person's would be too, from the
first identity run on, for good; only their mail DOMAIN stays
encrypted. That is theirs to agree to, knowing it, not something the
walk should do to a colleague on the strength of a marker. Claude
asks you how to go on before writing 13b.

(Your decision, 2026-10-08: "Second person, with consent". So the
person is told exactly the paragraph above before they are named, and
says yes to THAT.)

**13b. A second person joins the group.** In the container. The
person needs an Okta account in your org and an OPA user in the team
`nos-coastal-modeling-cloud-sandbox`; their `name` here is their bare
OPA username, as yours is. They are added as a MEMBER: they may log
in, without sudo. Their name is never typed into the chat, and the
lines below are written so that what you paste back to Claude does
not carry it; before you paste anything, look it over, and where a
name shows write `SECOND` in its place.

1. Three markers. Each command starts with a SPACE, so the values
   stay out of the shell history:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
    just cli encrypt 'THEIR-OPA-USERNAME'
    just cli encrypt 'THEIR-FIRST-NAME'
    just cli encrypt 'THEIR-LAST-NAME'
   ```

   If their Okta login does NOT end in the same mail domain as yours,
   a fourth: ` just cli encrypt 'THEIR-WHOLE-OKTA-LOGIN'` (again with
   the leading space).

2. Two edits, with the editor.

   In `groups/users.yaml`, a second entry under `users:`, shaped like
   yours:

   ```yaml
     - name: ENC[age:...]              # the first marker
       first_name: ENC[age:...]        # the second
       last_name: ENC[age:...]         # the third
   ```

   and, only if you made the fourth marker, one more line in that
   entry: `    email: ENC[age:...]`.

   In `groups/groups.yaml`, in `walk_team`, a `members:` list beside
   `admins:` (same indentation as `admins:`), holding the first
   marker again:

   ```yaml
       members:
         - ENC[age:...]                # the first marker
   ```

3. The identity run: OPA learns the membership.

   ```sh
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just validate
   just dry identity
   just run identity 2>&1 | tee ~/identity-13b.log | tail -3
   grep -nE 'Plan:|Apply complete|No changes\.|CI login policy|completed:|FAILED' ~/identity-13b.log | cut -c1-160
   ```

   The plan should add ONE thing and destroy nothing: the person's
   attachment to the OPA group `walk_team_user`. Claude has not seen
   a member added in this tree; paste the `grep`'s lines as they are
   (they carry no name). If the run fails, the reason is probably a
   name: a person Okta does not find under `<name>@<your domain>`
   (then make the fourth marker of step 1), or one OPA does not have
   in this team. Say which the error names, without the name.

4. The launch run: the machine learns the member list. Nothing is
   launched; an applying instance run is simply what carries a
   membership to the machines that stand.

   ```sh
   just cloud-launch aws-main 2>&1 | tee ~/launch-13b.log | tail -3
   grep -nE 'Plan:|No changes\.|Apply complete|accounts of group|completed:|FAILED' ~/launch-13b.log | cut -c1-160
   ```

   Expect the instance plan to say `No changes`, and `Instance
   walk-node-1: the accounts of group walk_team are in place`.

5. On the machine. The group's member list is a file, one name a
   line, which the login hook reads; these lines count without
   printing a name:

   ```sh
   sft ssh walk-node-1 --command 'sudo wc -l < /etc/csis/groups/walk_team.members; getent group walk_team | cut -d: -f4 | tr "," "\n" | grep -c .'
   ```

   Two numbers. The first should be `2`: you and the second person
   are on the list. The second should still be `1`: the daily driver
   says a member added "joins at their next login after that run",
   and they have not logged in. If they are willing to log in once
   from their own machine (`sft ssh walk-node-1`, nothing more), run
   the line again afterwards and the second number should be `2`;
   if not, say so and that half stays read, not walked.

6. Record it and let CI look, on `develop` only for now:

   ```sh
   just record
   git status --short                         # nothing listed
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch develop --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "CI on develop: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
   ```

   This is the push that publishes the person's username.

**Report:** `stage 13b done` with the two `grep` outputs (steps 3 and
4), the numbers of step 5 (and whether the person logged in), and the
`CI on develop:` line. Then STOP: 13c, taking them out again, is
written from what these runs said.

**What happened at 13b (2026-10-08): the membership reached OPA and
the machine's list, the person logged in, and the group did not take
them. It was the system's fault** (finding F37).

- `just run identity`: `Plan: 1 to add, 0 to change, 0 to destroy`,
  `Apply complete! Resources: 1 added`; the CI policy `unchanged`.
- After the launch run, the count on the machine: `2` names on the
  member list, `1` member of the group, as expected before a login.
- The second person then logged in with `sft ssh walk-node-1`, and
  the count stayed `2` and `1`. They were in, and not in the group.

Why. OPA's agent makes a person's account on a machine under their
`unix_user_name`, an ATTRIBUTE OPA keeps for each user, set there or
pushed from Okta; it is a value of its own and need not be the
person's OPA username. For you the two are the same word. For the
second person they are not. The login hook joins a person to a group
when the account that logs in is on the group's member list, name
for name; the list was written in OPA usernames; their account's
name was not on it. Nothing in the walk before this could have shown
it, because the walk had one person, whose two names agree. The
reference configuration carries the same exposure for the same
reason.

By your decision ("Fix it in the system now") this is stage 87: the
member list, and a key file's name, are written in account names,
each READ from OPA at that moment. Nothing is derived: your word was
"You cannot depend on translating _ to . and vice versa", and no
name is computed from another by any rule. A person whose attribute
OPA does not give stops the list from being rewritten at all, and
the machine stays as it stands.

**13b again: release 0.1.1.dev20, take it, the list rewritten.**
Stage 87 is merged. Where 13b stands in the walk tree: the two runs
of 13b committed their records (two commits, not pushed), and your
two edits to `groups/` are NOT committed yet: a run commits
`generated/` and `meta-state/`, never your declarations, and 13b's
step 6, which this page wrote without the line that commits them,
was not reached. Step 2 below commits them. Nothing with the second
person's name has left the container so far.

1. **On your local machine (the host, NOT the container): cut
   release 0.1.1.dev20 from `develop`.** `develop` says dev19 now, so
   the plain `dev` form is right again. Line by line; the guarded
   lines print `OK` or `STOP`:

   ```sh
   cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3 2>/dev/null && [ -d packages/base ] && echo "OK: local machine, the system repository, $(pwd)" || echo "STOP: this is the container, or the path is wrong"
   git status --short                         # nothing listed
   git checkout develop && git pull
   [ "$(git branch --show-current)" = develop ] && echo "OK: on develop, at: $(git log --oneline -1)" || echo "STOP: not on develop"
   ```

   The second `OK` line must end with the stage 87 squash, `A group
   on a machine lists its members by account name (stage 87)`. Then:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' https://test.pypi.org/legacy/   # 200: the index can take an upload
   [ "$(git branch --show-current)" = develop ] && just release dev test yes || echo "STOP: not on develop"   # dry: 0.1.1.dev19 would become 0.1.1.dev20
   [ "$(git branch --show-current)" = develop ] && just release dev test || echo "STOP: not on develop"       # the bar (about 28 minutes), the upload, the commit, the tag
   git log --oneline -1                       # release 0.1.1.dev20
   git push --follow-tags
   git checkout feature/walk-daily-driver     # brings this document back
   ```

   **Report:** `dev20 pushed`. Claude confirms it is on `develop` and
   on the index, takes it into the reference configuration, and says
   go for step 2.

   (DONE 2026-10-08: release commit 8c0a822 is on `develop` with the
   tag `v0.1.1.dev20`; 18 of 18 packages are on the index. Go for
   step 2.)

2. **In the container: your declarations, then the release.** The
   release is out (see above):

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status --short                         # expect exactly: M groups/groups.yaml and M groups/users.yaml
   git add groups/groups.yaml groups/users.yaml && git commit -m "A second member of walk_team"
   uv tool install --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ "cs-image-system==0.1.1.dev20"
   uv tool list                               # cs-image-system v0.1.1.dev20
   [ "$(pwd)" = /walk/cs-image-system-walk ] && [ -f cfg/_config.yml ] && cs-image-system init-config . --force || echo "STOP: not the walk tree in the container"
   cat .csis-version                          # 0.1.1.dev20
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just validate
   just dry
   git add -A && git commit -m "Take release 0.1.1.dev20: a group's members are listed by account name"
   ```

3. **The launch run again, and the count.** This is the run that
   rewrites the member list on the machine, now in account names:

   ```sh
   just cloud-launch aws-main 2>&1 | tee ~/launch-13b2.log | tail -3
   grep -nE 'Plan:|No changes\.|accounts of group|could not be made|completed:|FAILED' ~/launch-13b2.log | cut -c1-160
   sft ssh walk-node-1 --command 'sudo wc -l < /etc/csis/groups/walk_team.members; getent group walk_team | cut -d: -f4 | tr "," "\n" | grep -c .'
   ```

   The `grep` should show `the accounts of group walk_team are in
   place` and no `could not be made`. The two numbers should be `2`
   and `2`: the script also joins, at once, every listed person whose
   account stands on the machine, and the second person's does since
   their login. If they read `2` and `1`, the account has gone in the
   meantime (OPA's agent removes accounts it made); ask the second
   person to log in once more and run the count again. Either way
   report the numbers you saw, in order.

   (2026-10-08: the launch run said `No changes` and `the accounts of
   group walk_team are in place`, and the numbers read `2` and `1`.
   That alone does not say whether the fix works: `getent` shows a
   person only while their account stands on the machine, and OPA's
   agent removes an account some time after its owner has gone. Step
   3b tells the two cases apart.)

3b. **Is the listed name an account, and does a login carry the
   group?** Three looks, none of which prints a name.

   First, you, in the container: for each name on the list, does an
   account of exactly that name stand on the machine now?

   ```sh
   sft ssh walk-node-1 --command 'for n in $(sudo cat /etc/csis/groups/walk_team.members); do getent passwd "$n" >/dev/null && echo account-stands || echo no-account; done'
   ```

   Two lines. One is yours and says `account-stands`. If the other
   says `no-account`, the second person has no account on the
   machine at this moment, which is why they are not in the group.

   Second, the second person, from their own machine, logs in and
   asks their own session whether it carries the group:

   ```sh
   sft ssh walk-node-1 --command 'id -nG | tr " " "\n" | grep -c "^walk_team$"'
   ```

   `1` is the proof of stage 87: their login joined the group. `0`
   means it did not.

   Third, you again, straight after their login, the first line of
   this step once more and then the count:

   ```sh
   sft ssh walk-node-1 --command 'for n in $(sudo cat /etc/csis/groups/walk_team.members); do getent passwd "$n" >/dev/null && echo account-stands || echo no-account; done'
   sft ssh walk-node-1 --command 'sudo wc -l < /etc/csis/groups/walk_team.members; getent group walk_team | cut -d: -f4 | tr "," "\n" | grep -c .'
   ```

   Now both lines should say `account-stands`: the name on the list
   IS their account's name, which before the fix it was not. And the
   count should read `2` and `2`.

4. **Record, push, CI**, on `develop` only:

   ```sh
   just record
   git status --short                         # nothing listed
   git push
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch develop --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "CI on develop: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
   ```

   This is the push that publishes the second person's username, as
   they agreed.

**Report:** `stage 13b done` with step 3's `grep` output, the numbers
(and whether a second login was needed), what the three looks of
step 3b printed, and the `CI on develop:` line. If CI says `success`,
go straight on to 13c.

**What happened at "13b again" (2026-10-08): stage 87 is proved by
the login it was written for.** The second person's own session,
asked whether it carries `walk_team`, answered `1`. Before the fix
they logged in and were not in the group; after it, their login
joins it.

Your two lines straight afterwards read `account-stands`,
`no-account`, then `2` and `1`, and that is right too; it was this
page's expectation of `2` and `2` that was wrong. OPA's agent makes a
person's account for their session and takes it away again when they
are gone: by the time you looked, theirs no longer stood, so
`getent` had nobody to show beside you. A person is visible in the
group on a machine only while they are on it. You would see `2` and
`2` only by looking while they are still logged in, and nothing
needs that look now. (Earlier you remarked that Okta seems to take a
minute or three to push accounts down; this page cannot say which
part of that is the agent learning of a new member and which is the
account itself. What it can say is what was seen: an account that
stood during a session and not after it.)

**13c. The second person leaves the group again.** In the container.
The daily driver's row "Who may log in" in reverse: the membership
goes from the YAML, the identity run takes it out of OPA, a launch
run takes the name off the machine's list. Their username stays in
this repository's history, as they agreed; nothing can take that
back.

1. Two edits, with the editor, undoing 13b's. In
   `groups/groups.yaml`, delete the whole `members:` list of
   `walk_team` (the `members:` line and the marker under it). In
   `groups/users.yaml`, delete the second person's entry (the `-
   name:` line and the lines under it, down to but not including
   yours or the end of the file). Then:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status --short                         # expect exactly: M groups/groups.yaml and M groups/users.yaml
   git diff --stat                            # deletions only
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just validate
   git add groups/groups.yaml groups/users.yaml && git commit -m "walk_team has one person again"
   ```

2. The identity run. This time the plan DESTROYS one thing, the
   person's attachment to `walk_team_user`, and the gate has to let
   exactly that through. Claude has not seen a membership removed in
   this tree; whatever the gate says is what this step is for:

   ```sh
   just dry identity
   grep -n 'gate-plan' generated/identity/run-identity.sh | cut -c1-220    # does the gate line name a destroy it will allow?
   just run identity 2>&1 | tee ~/identity-13c.log | tail -3
   grep -nE 'Plan:|gate|REFUS|refus|Apply complete|No changes\.|completed:|FAILED' ~/identity-13c.log | cut -c1-200
   ```

   If the gate refuses the plan, STOP and paste the `grep`'s lines,
   with `SECOND` in place of any name: nothing was changed, and that
   refusal is a finding, not an error of yours.

   (2026-10-08: it refused. The runner's prune step said `member
   'SECOND' was dropped from group 'walk_team' but OPA still holds
   it; the plan will show the destroy`; the plan said `0 to add, 0 to
   change, 1 to destroy`; and the gate stopped the run: `DESTROY NOT
   WHITELISTED: module.group_walk_team.oktapam_user_group_attachment.
   members["SECOND"]`, exit 3, `Run ... FAILED: LifecycleRunError:
   Apply failed for lifecycle identity`. Nothing was applied.)

   This is the system doing what it is built to do, and the pages
   not saying so (finding F38). The system never takes a person's
   access away on the strength of a YAML edit alone: the operations
   guide's own rule is "membership removals only by explicit
   decision", and the gate allows no destroy of a membership at all.
   The decision is made where the membership lives, in OPA, by a
   person; the system then tidies its own state. The daily driver
   says of a removal that "the plan shows the destroy and the gate
   sees it", which reads as though it goes through. It does not.

   **Your decision on reading this (2026-10-08): the rule itself was
   a mistake.** "The system can add users to an oktapam group. It
   should be able to remove them from that group, as well." So this
   is no longer only words: stage 88 changes the system. From
   0.1.1.dev21 a member dropped from the YAML is removed from the OPA
   group by the identity run: the runner names the attachment of each
   membership the declaration dropped, and the gate lets exactly
   those through. Nothing else becomes destroyable: not a group, a
   user, a policy or a token, and not a person the YAML still names.
   Step 2b below is still the way on TODAY's release, and it is half
   done already. Stage 88 is merged (20206e8); 13d, below, repeats the
   removal on the new release, by the YAML alone.

2b. **The explicit decision, then the run again.**

   You, in the OPA console: open the group `walk_team_user` (the
   members' group of `walk_team`; `walk_team_admin` is the admins'
   and is not touched) and remove the second person from it.

   Then, in the container, the identity run once more:

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status -sb                             # develop, ahead 1 (your commit of step 1), nothing else listed
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just run identity 2>&1 | tee ~/identity-13c2.log | tail -3
   grep -nE 'Plan:|No changes\.|no longer holds|still holds|state rm|backup|NOT WHITELISTED|Apply complete|completed:|FAILED' ~/identity-13c2.log | sed -E 's/(member|admin) .[^ ]*. was/\1 SECOND was/; s/\["[^"]*"\]/["SECOND"]/g' | cut -c1-200
   ```

   What should happen now, by the operations guide ("Drop a
   membership"): the prune step finds that OPA no longer holds the
   membership, backs the state up, and takes the attachment out of
   terraform state itself (`... and OPA no longer holds it; its
   attachment leaves tofu state before the plan: state rm ...`); the
   plan then says `No changes`, the gate has nothing to refuse, and
   the run completes. The `sed` in the last line writes `SECOND`
   where the log names the person; look the output over all the same
   before you paste it. If the prune step still says `OPA still
   holds it`, the console change has not reached OPA's API yet: wait
   a minute and run the two lines again.

   (2026-10-08: it did, line for line. `state backup for workspace
   'opa-groups': serial 2, 10 resource(s)`; then `member 'SECOND'
   was dropped from group 'walk_team' and OPA no longer holds it;
   its attachment leaves tofu state before the plan: state rm ...`;
   the runner's plan said `No changes`, the gate `Plan passes the
   apply gate`, the apply `0 added, 0 changed, 0 destroyed`, and the
   run completed and committed its record, 3ce4cc6.

   Your `grep` also shows, EARLIER in the log, `Plan: 0 to add, 0 to
   change, 1 to destroy`. That plan was not applied, and nothing
   was destroyed. An applying run plans the group root twice. The
   first is a preview, made while the run writes the root: it is
   not saved (tofu's own note under it says `You didn't use the
   -out option`), it does not refresh, and nothing reads it. The
   second is the runner's, made after the prune step and saved; it
   is the one the gate reads and the apply takes. The preview came
   before the prune step, so it still saw the attachment in state.
   The operations guide says this in a clause under "Drop a
   membership"; the daily driver does not say it at all, and the
   log gives the reader a destroy that never happens (finding
   F39).)

3. The launch run, and the machine's list:

   ```sh
   just cloud-launch aws-main 2>&1 | tee ~/launch-13c.log | tail -3
   grep -nE 'No changes\.|accounts of group|could not be made|completed:|FAILED' ~/launch-13c.log | cut -c1-160
   sft ssh walk-node-1 --command 'sudo wc -l < /etc/csis/groups/walk_team.members; getent group walk_team | cut -d: -f4 | tr "," "\n" | grep -c .'
   ```

   Expect `the accounts of group walk_team are in place`, then `1`
   and `1`: one name on the list, yours, and you in the group.

   If the second person is willing, one last thing from their own
   machine: `sft ssh walk-node-1` should now be REFUSED. OPA may take
   a few minutes to stop honouring an access it has just withdrawn.
   Say what they saw, or that it was not tried.

4. Record, push, and let `main` see it:

   ```sh
   just record
   git status --short                         # nothing listed
   git push
   git push origin develop:main
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "perform on main: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
   git fetch origin && git merge --ff-only origin/main && git push
   ```

**Report:** `stage 13c done` with step 2b's `grep` output, step 3's
`grep` and numbers, what the second person saw (or `not tried`), and
the `perform on main:` line. 13d follows.

(DONE 2026-10-08. The launch run of step 3 is recorded as completed,
walk commit c3cbaad. `perform on main: success at b1cce04`, and its
log says `login proof walk-node-1: login: ok`, `logged in as
wl_cs_image_system_walk_ci`, and `no drift: meta-state agrees with
reality` at its start and its end; it pushed its three records and
`develop`, `origin/develop` and `origin/main` now agree. The second
person's refused login was not tried. Step 3's two numbers were not
reported, and Claude cannot read them back: `~/launch-13c.log` was
written again at 23:51 UTC by a launch that was cut short after 24
lines and recorded nothing. Nothing in 13d depends on them.)

**13d. The same removal, by the YAML alone (the proof of stage 88).**
Stage 88 is merged: a membership the YAML drops is removed from the
OPA group by the identity run itself. This part proves it where 13c
found the need: the second person goes back into `walk_team` for one
run and comes out again by an edit and a run, with nobody opening
the OPA console. Tell them first; it is the same membership they
agreed to, for a few minutes more. Nothing is typed with their name
in it: both edits are taken from this repository's own history.

Step 1, the release, is on your local machine and does not wait for
13c. Steps 2 to 6 do: they start, in the container, from a walk tree
that is clean and pushed, after `stage 13c done`.

1. **On your local machine (the host, NOT the container): cut
   release 0.1.1.dev21 from `develop`.** `develop` says dev20 now, so
   the plain `dev` form is right. Line by line; the guarded lines
   print `OK` or `STOP`:

   ```sh
   cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3 2>/dev/null && [ -d packages/base ] && echo "OK: local machine, the system repository, $(pwd)" || echo "STOP: this is the container, or the path is wrong"
   git status --short                         # nothing listed
   git checkout develop && git pull
   [ "$(git branch --show-current)" = develop ] && echo "OK: on develop, at: $(git log --oneline -1)" || echo "STOP: not on develop"
   ```

   The second `OK` line must end with the stage 88 squash, `A
   membership the YAML dropped is removed by the run (stage 88)`.
   Then:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' https://test.pypi.org/legacy/   # 200: the index can take an upload
   [ "$(git branch --show-current)" = develop ] && just release dev test yes || echo "STOP: not on develop"   # dry: 0.1.1.dev20 would become 0.1.1.dev21
   [ "$(git branch --show-current)" = develop ] && just release dev test || echo "STOP: not on develop"       # the bar (about 28 minutes), the upload, the commit, the tag
   git log --oneline -1                       # release 0.1.1.dev21
   git push --follow-tags
   git checkout feature/walk-daily-driver     # brings this document back
   aws sso login --profile noaa               # Claude's local session ended at 21:34 UTC on 2026-10-08; the reference configuration's dry run needs one
   ```

   **Report:** `dev21 pushed`. Claude confirms it is on `develop` and
   on the index, takes it into the reference configuration, and says
   go for step 2.

   (DONE 2026-10-08: release commit 40f3efc is on `develop` with the
   tag `v0.1.1.dev21`; 18 of 18 packages are on the index. The
   reference configuration took it on its `develop`: no
   release-owned file changed but the version, and its emission
   moved by the one line this stage is about, the identity runner's
   gate. Go for step 2.)

2. **In the container: take the release.**

   ```sh
   cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
   git status -sb                             # develop, level with origin, nothing listed (13c is done and pushed)
   uv tool install --index-url https://test.pypi.org/simple/ \
     --extra-index-url https://pypi.org/simple/ "cs-image-system==0.1.1.dev21"
   uv tool list                               # cs-image-system v0.1.1.dev21
   [ "$(pwd)" = /walk/cs-image-system-walk ] && [ -f cfg/_config.yml ] && cs-image-system init-config . --force || echo "STOP: not the walk tree in the container"
   cat .csis-version                          # 0.1.1.dev21
   aws sts get-caller-identity                # keys live? refresh them first if they are near an hour old
   just validate
   just dry
   grep -n 'gate-plan' generated/identity/run-identity.sh | cut -c1-260
   git add -A && git commit -m "Take release 0.1.1.dev21: a membership the YAML dropped is removed by the run"
   ```

   The `grep` is the first sight of the change. The gate line of
   the root `opa-groups/group-generation` should now end
   `--allow-destroy-from csis-sanctioned-removals.txt`, and the
   `okta-users` root's gate line should not have it: the file is
   where the runner's own step names, at run time, the attachment of
   each membership the YAML dropped, and only the root that holds
   memberships reads one.

   (2026-10-09: the committed runner has ONE gate line, and it ends
   that way. This page was wrong to speak of a second: the
   `okta-users` root holds only lookups of people, is never applied,
   and so has no gate at all.)

3. **The second person back in, from history.** The commit `9c8bc06`
   ("A second member of walk_team") holds both files as they were
   with two people:

   ```sh
   git checkout 9c8bc06 -- groups/groups.yaml groups/users.yaml
   git status --short                         # expect exactly: M  groups/groups.yaml and M  groups/users.yaml
   just validate
   git commit -m "A second member of walk_team, for one run"
   just run identity 2>&1 | tee ~/identity-13d-add.log | tail -3
   grep -nE 'Plan:|Apply complete|No changes\.|completed:|FAILED' ~/identity-13d-add.log | cut -c1-160
   ```

   As in 13b: `Plan: 1 to add, 0 to change, 0 to destroy`, probably
   twice (the preview, then the runner's own plan; see 13c step 2b),
   and `Apply complete! Resources: 1 added`. They are a member of
   `walk_team_user` in OPA again. No launch run follows, on purpose:
   the machine's own list is not rewritten, and stays as 13c left it.

4. **And out again, by the YAML alone.** `9c8bc06~1` is the commit
   before that one: both files with you alone.

   ```sh
   git checkout 9c8bc06~1 -- groups/groups.yaml groups/users.yaml
   git status --short                         # expect exactly: M  groups/groups.yaml and M  groups/users.yaml
   just validate
   git commit -m "walk_team has one person again, by the YAML alone"
   just run identity 2>&1 | tee ~/identity-13d.log | tail -3
   grep -nE 'Plan:|still holds|sanctioned|NOT WHITELISTED|passes the apply gate|Apply complete|completed:|FAILED' ~/identity-13d.log | sed -E 's/(member|admin) .[^ ]*. was/\1 SECOND was/; s/\["[^"]*"\]/["SECOND"]/g' | cut -c1-220
   ```

   This is the run that failed at 13c. What stage 88's tests say it
   prints now, none of it seen in this tree yet, which is what the
   step is for:

   - the prune step: `member 'SECOND' was dropped from group
     'walk_team' and OPA still holds it; the plan will show the
     destroy of its attachment, which the declaration asks for and
     the gate allows`;
   - the plan: `Plan: 0 to add, 0 to change, 1 to destroy`, twice,
     the preview before the prune step's line and the runner's own
     after it, and this time the second one is real;
   - the gate: `Destroy sanctioned by the declaration:
     module.group_walk_team.oktapam_user_group_attachment.
     members["SECOND"]`, then `Plan passes the apply gate.`;
   - the apply: `Apply complete! Resources: 0 added, 0 changed, 1
     destroyed`, and the run `completed: identity`.

   The `sed` writes `SECOND` where the log names the person; look
   the output over all the same before you paste it. If the gate
   says `DESTROY NOT WHITELISTED` instead, STOP and paste the lines:
   nothing was changed, and the fix does not do what its tests say.

   (2026-10-09, 00:56 UTC: it did what its tests say, line for line.
   The add run of step 3 said `Plan: 1 to add, 0 to change, 0 to
   destroy` twice and `Apply complete! Resources: 1 added`. Then
   this run: the preview, `Plan: 0 to add, 0 to change, 1 to
   destroy`; the prune step, `member 'SECOND' was dropped from
   group 'walk_team' and OPA still holds it; the plan will show the
   destroy of its ...`, which is OPA's own API saying, at that
   moment, that the person WAS a member; the runner's plan, `1 to
   destroy` again; the gate, `Destroy sanctioned by the
   declaration: module.group_walk_team.
   oktapam_user_group_attachment.members["SECOND"]` and `Plan
   passes the apply gate.`; the apply, `0 added, 0 changed, 1
   destroyed`; `Run ... completed: identity`. The same run on
   0.1.1.dev20, at 13c, stopped at the gate.)

5. **OPA's own word.** In the OPA console, open the group
   `walk_team_user`: the second person is not in it, and you did not
   take them out. Say what you see. (Claude reads the same group
   from OPA's API, a count and no names, when you report.) If the
   second person is willing, `sft ssh walk-node-1` from their own
   machine should be refused, perhaps only after a few minutes.

   (2026-10-09: you, in the console: `walk_team_user` has no
   members. Claude, from OPA's API with the service's read-only
   pair: `walk_team_user` 0 members, `walk_team_admin` 1. Nobody
   opened the console to take the person out. A member the YAML
   adds, the run adds; a member the YAML drops, the run removes.
   Stage 88 is proved.)

6. Record, push, and let `main` see it:

   ```sh
   just record
   git status --short                         # nothing listed
   git push
   git push origin develop:main
   run=""
   for i in $(seq 12); do
     sleep 5
     run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
     [ -n "$run" ] && break
   done
   echo "run ${run:-NOT FOUND after 60 seconds}"
   [ -n "$run" ] && gh run watch "$run"
   echo "perform on main: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
   git fetch origin && git merge --ff-only origin/main && git push
   ```

**Report:** `stage 13 done` with step 2's `grep` (the gate lines),
step 3's `grep`, step 4's `grep`, what the console shows, what the
second person saw (or `not tried`), and the `perform on main:` line.

(STAGE 13 DONE 2026-10-09. `perform on main: success at 753bb65`:
its three jobs each installed `cs-image-system==0.1.1.dev21`; the
workload's proof says `login proof walk-node-1: login: ok`; the
strict state query says `no drift: meta-state agrees with reality`
before and after. The walk's `develop`, `origin/develop` and
`origin/main` agree at f4ff216, and `walk_team` has its one person.
The second person's refused login was not tried in 13c or 13d: that
a removed member can no longer log in is read from OPA's group, not
walked.)

## Stage 14 -- the failure walk (DAILY_DRIVER 6)

Read the daily driver's section 6, "When it fails": its first
paragraph (where to look) and the table. This stage provokes
failures on purpose and holds each against the page: is the symptom
what the system prints, is the meaning right, does the remedy work.

All of it is in the container. Parts 14a to 14e change nothing
outside your working tree: each makes a one-line edit or types a
command that is refused, reads what the system says, and puts the
tree back, ending on a `git status --short` that lists nothing.
Only 14f touches the cloud, and what it touches is the machine's
power. Nothing is committed until 14g.

| Part | The failure | Where the daily driver speaks of it |
| --- | --- | --- |
| 14a | a session that has ended | the row `preflight: a session has EXPIRED` |
| 14b | a shell that never loaded `.envrc` | the row `OPA credentials for team '<t>' not found in the environment` |
| 14c | a reserved name, `name: none` | no row; section 3 says the words are reserved |
| 14d | an `--only` name that `--only-runtime` cannot honour | no row |
| 14e | a pin to an unreleased build, outside the grace | the row `instance 'x' is pinned to build ...` |
| 14f | a machine someone switched off | the row `verify ...: SKIPPED -- the machine is STOPPED` |
| (done) | a destroy the gate must refuse | the row `DESTROY NOT WHITELISTED: <address>` |

**The last of them you have walked already**, at 13c on
0.1.1.dev20, without meaning to: `DESTROY NOT WHITELISTED:
module.group_walk_team.oktapam_user_group_attachment.
members["SECOND"]`, exit 3, the run FAILED, nothing applied. Symptom
and meaning were the row's. It is not provoked again, for a reason
worth knowing: this tree has no SAFE way left to do it. A dropped
membership is now removed by design (stage 88). And the obvious
trick, deleting an entry to watch the gate object, is not a failure
at all. **Deleting an instance's entry is how an instance is
decommissioned** (the daily driver's section 4: "delete the entry
... the gate whitelists exactly its destroy"), and the next launch
run would destroy `walk-node-1` with the gate's blessing. Do not
delete an entry to test the gate.

Where this page quotes what a command "said", Claude typed the same
thing on 2026-10-09 into a private copy of the REFERENCE
configuration, on this release, and read the answer. Your tree's
names differ and the sentence should not. Where it says Claude does
not know, that is the point of the step.

**14a. A session that has ended.** For this one the keys must have
lapsed by themselves, so it is done BEFORE you refresh them:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
git status -sb                             # develop, level with origin, nothing listed
aws sts get-caller-identity 2>&1 | tail -1 | cut -c1-160
```

If the last line shows your account, the keys are still live: skip
14a, go on to 14b, and do 14a at the start of your next sitting,
before refreshing them. If it shows an error, go on:

```sh
just preflight 2>&1 | tail -2 | cut -c1-200
just validate 2>&1 | tail -5 | cut -c1-200
just cloud-preflight 2>&1 | tail -5 | cut -c1-200
```

Then refresh the keys as in stage 3 and check them:

```sh
aws sts get-caller-identity --query Account --output text   # 514190660293
```

The page's row is written for an SSO profile: it expects `preflight`
to say `a session has EXPIRED` and its remedy is `aws sso login`.
Your container holds access keys in a credentials file instead, of
which `preflight` can only say `profile 'noaa' is not an SSO profile
(no expiry readable)`; at stage 11 a lapsed key showed itself as a
`RequestExpired` traceback out of `just validate` (finding F30).
Paste the three tails: they are what a team with keys would meet.

(DONE 2026-10-09, with the keys truly lapsed: `aws sts` said
`ExpiredToken`. Held against the page's row:

- **Symptom: not the row's.** `just preflight` said `session:
  aws-main (aws, profile noaa): profile 'noaa' is not an SSO profile
  (no expiry readable)` and then, in green, `preflight: every
  session present`, over keys that were dead (finding F40). `just
  validate` and `just cloud-preflight` each ended in a traceback and
  `ValueError: AWS Error: An error occurred (RequestExpired) when
  calling the DescribeVpcs operation: Request has expired.`, exit 1.
  The row shows three other sentences, all an SSO profile's. This
  is finding F30 again, this time on purpose.
- **Meaning: the row's.** Environmental; nothing of the system's or
  the tree's was wrong.
- **Remedy: not the row's.** `aws sso login` does nothing for a key
  profile. Fresh keys in `~/.aws/credentials` did: the account
  number came back.)

**14b. A shell that never loaded `.envrc`.** Two lines. The first
runs `validate` in a shell with nothing in it but your home and your
path; the second in your own shell with only the OPA pair taken out:

```sh
env -i HOME="$HOME" PATH="$PATH" bash -c 'cd /walk/cs-image-system-walk && just validate' 2>&1 | tail -6 | cut -c1-200
env -u TF_VAR_nos_coastal_modeling_cloud_sandbox_key -u TF_VAR_nos_coastal_modeling_cloud_sandbox_secret just validate 2>&1 | tail -4 | cut -c1-200
git status --short                         # nothing listed
```

In the copy the first said `MissingIdentityError: <tree>/cfg:
user_builders[0].email_domain: an encrypted value is present but
CSIS_CONFIG_IDENTITY is not set -- export the age identity (...)`,
and the second `ValueError: Okta builder oktagroups is missing a key
value. Expected to find environment variable TF_VAR_<team>_key for
team <team> in org <org>`. Neither is the sentence in the page's
row, and the first has no row. Both name variables, never a value;
look the lines over before you paste them all the same.

(DONE 2026-10-09: both said what the copy said, each under a
traceback, exit 1, and the tree stayed clean. Held against the
page:

- **The empty shell:** `MissingIdentityError:
  /walk/cs-image-system-walk/cfg: user_builders[0].email_domain: an
  encrypted value is present but CSIS_CONFIG_IDENTITY is not set --
  export the age identity (...)`. This is the FIRST thing a shell
  without `.envrc` meets in any tree that holds an encrypted value,
  which every starter's does, and section 6 has no row for it
  (finding F41). The sentence itself says what to do, and doing it
  (your own shell, with `.envrc` loaded) is the remedy.
- **Without the OPA pair:** `ValueError: Okta builder opa-groups is
  missing a key value. Expected to find environment variable
  TF_VAR_nos_coastal_modeling_cloud_sandbox_key for team ... in org
  noaa`. The row's meaning and remedy are right; the sentence it
  quotes is not the one printed. That is finding F10, from stage 7,
  met again on purpose.)

**14c. A reserved name.** One instance is renamed `none` in the
working tree, and put back:

```sh
sed -i 's/^  - name: walk-node-1 /  - name: none /' instances/instances.yaml
git diff --stat                            # instances/instances.yaml | 2 +-
just validate 2>&1 | tail -5 | cut -c1-200
git checkout -- instances/instances.yaml && git status --short    # nothing listed
```

In the copy: `ReservedNameError: <tree>/instances/instances.yaml:
instances[1].name: a name may not be 'none'`, then the reason in
brackets (the words `default`, `self`, `none`, the empty string and
null mean "not set" wherever a value is read). Yours should say
`instances[0]`.

(DONE 2026-10-09: `ReservedNameError:
/walk/cs-image-system-walk/instances/instances.yaml:
instances[0].name: a name may not be 'none'`, the reason in
brackets, exit 1; the file put back, the tree clean. The daily
driver's section 3 promises that "the refusal names the file, the
entry and the word", and it does, all three. Two things for the
words: section 6 has no row for it, and it arrives under a
traceback and not as a line under `Validation failed with N
error(s)`, which is how that table says a rule that failed before
anything was generated shows itself (finding F42).)

**14d. `--only` beside `--only-runtime`.** Three refused commands.
They are dry runs (no `--no-dry-run`), so even one that was not
refused would execute nothing:

```sh
just cli run instance-image --only team-node@elsewhere --only-runtime aws-main 2>&1 | tail -2 | cut -c1-240
just cli run instance-image --only nosuch --only-runtime aws-main 2>&1 | tail -2 | cut -c1-240
just cli run instance-image --only-runtime nosuch 2>&1 | tail -2 | cut -c1-240
git status --short                         # nothing listed: each was refused before a file was written
```

In the copy, in order: `--only-runtime: --only <image>@<other>
names runtime '<other>', outside --only-runtime '<runtime>' (baked
on <runtime>: <its images>)`; `--only-runtime: --only nosuch-image
is not baked on '<runtime>' (baked on ...)`; `--only-runtime:
unknown runtime 'nosuch'`. Each ended with exit code 2, which here
`just` reports in a line of its own under the message. If the last
`git status` does list files, one of them was not refused: say so,
and `git checkout -- generated meta-state` puts them back.

(DONE 2026-10-09: three refusals, one line each, exit 2, the tree
clean. `--only-runtime: --only team-node@elsewhere names runtime
'elsewhere', outside --only-runtime 'aws-main' (baked on aws-main:
el10, team-node)`; `--only-runtime: --only nosuch is not baked on
'aws-main' (baked on aws-main: el10, team-node)`; `--only-runtime:
unknown runtime 'nosuch'`. No finding. These are the best-behaved
refusals of the stage: no traceback, each says what is wrong and
what the runtime does bake, and nothing was written. Section 6 has
no row for them and they need none; the flags themselves are the
operations guide's, and the daily driver's recipes never ask you
to type them.)

**14e. A pin to an unreleased build.** This tree does not use the
rule. The starter leaves `require_released_builds` out of
`cfg/_config.yml`, and its image declares no `release:`, so the
page's row cannot happen here as the tree stands. This part
switches the rule on for a minute, in the working tree only, and
then moves the machine's pin to the OLDER build of `team-node`:

```sh
sed -i 's/^  apply_instances: false$/  apply_instances: false\n  require_released_builds: true/' cfg/_config.yml
git diff --stat                            # cfg/_config.yml | 1 +
just validate 2>&1 | tail -4 | cut -c1-300 # the pin as it stands: the machine's own build, the newest of its series
just cli upgrade instance walk-node-1 --to ami-03a8cef5e12cd1b50 2>&1 | tail -1 | cut -c1-200
just validate 2>&1 | tail -3 | cut -c1-400
git checkout -- cfg/_config.yml meta-state/pins.yaml && git status --short    # nothing listed
grep -n 'walk-node-1: ' meta-state/pins.yaml                                   # ami-04bb9df333af05e5b: the pin is back
```

**The last two lines matter more than the rest.** The pin move is
real in your working tree (it is the command `cloud-upgrade` begins
with). Left in place, the next launch run would REPLACE the machine
with the older build. `git status` must list nothing and the `grep`
must show `ami-04bb9df333af05e5b` before you go on. If either is
not so, STOP and say so.

What to expect. The first `validate`: Claude does not know. The
page says an unreleased pin is allowed for "the series head under
its own proof" (the release grace), and your machine stands on the
head of its series, so it should pass, perhaps with a warning that
names the grace; if it refuses, its reason is the finding. The
second, in the copy: `instance '<name>' is pinned to build <id> of
'<image>', which is not a released build
(config.require_released_builds; no grace: the build is not the head
of series '<image>' on its ...)` and `Validation failed with 1
error(s).`

(DONE 2026-10-09, and the pin is back: Claude read the tree from
the host afterwards, nothing changed, `walk-node-1:
ami-04bb9df333af05e5b`, no pending replacement, the rule gone from
`cfg/_config.yml`. Held against the page:

- **Under the grace** the first `validate` passed with `WARNING
  config.require_released_builds: build ami-04bb9df333af05e5b of
  'team-node' is not released yet, allowed under the release grace:
  'walk-node-1' stands on series head ami-04bb9df333af05e5b
  (launched; verify it, then release it)`. That is the page's
  "series head under its own proof", working as written.
- **Outside it** the second said `instance 'walk-node-1' is pinned
  to build ami-03a8cef5e12cd1b50 of 'team-node', which is not a
  released build (config.require_released_builds; no grace: the
  build is not the head of series 'team-node' on its runtime)` and
  `Validation failed with 1 error(s).`, exit 1, with no traceback.
  Symptom, meaning and remedy ("move the pin") are the row's. The
  row holds.
- **What the walk had to do to get there is the finding** (F43):
  the daily driver's 1.9 tells a team to settle
  `require_released_builds`, `require_image_tests` and
  `preflight.expected_run_minutes` in `cfg/_config.yml`, and the
  starter's file shows none of the three; nor does its image
  declare a `release:`, so the warning's advice, "verify it, then
  release it", has nothing in this tree to act on.)

**14f. A machine someone switched off.** The first time this walk
stops a machine. It needs live keys and a live `sft` session. Every
line below is typed in the CONTAINER's shell, none on the machine,
and each box sets `id` for itself, so a box can be started in a new
shell. (2026-10-09: the first try said `aws: command not found`. It
was typed on the machine itself, after an `sft ssh walk-node-1`:
the machine's prompt differs from the container's only in the
host's name, and the machine has no `aws`. The first line of each
box now says `STOP` there.)

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
aws sts get-caller-identity --query Account --output text   # 514190660293
sft list-teams                             # STATUS a time remaining; if Expired: sft login
id=$(grep -m1 'instance_id:' meta-state/instance-state.yaml | awk '{print $2}'); echo "$id"    # i-0792ba0408f0e1388
aws ec2 stop-instances --instance-ids "$id" --query 'StoppingInstances[0].CurrentState.Name' --output text
aws ec2 wait instance-stopped --instance-ids "$id" && echo "stopped"
```

If AWS refuses the stop (your role is a power user's, without
networking), say so and stop the machine in the EC2 console
instead; the rest is the same. With the machine off:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
id=$(grep -m1 'instance_id:' meta-state/instance-state.yaml | awk '{print $2}'); echo "$id"    # i-0792ba0408f0e1388
aws ec2 describe-instances --instance-ids "$id" --query 'Reservations[0].Instances[0].State.Name' --output text   # stopped
just state-query --strict 2>&1 | tail -6 | cut -c1-200
just cloud-verify aws-main walk-node-1 2>&1 | tail -4 | cut -c1-200
just ci-login-proof walk-node-1 2>&1 | tail -4 | cut -c1-200
aws ec2 describe-instances --instance-ids "$id" --query 'Reservations[0].Instances[0].State.Name' --output text
```

The page's row: a machine that is off is "a note, not drift", its
verify and its login proof are each `SKIPPED`, and "nothing is
started for a proof". So the strict state query should still pass,
the two proofs should say they were skipped and why, and the last
line should still say `stopped`. Claude has seen none of this in
your tree. If the last line says `running`, something started your
machine: that is a finding, and say which command came before it.

(DONE 2026-10-09, 10:25 to 10:27 UTC, and this page's test was too
weak to see what happened. Held against the page's row:

- **The state query: the row's.** `note: instances/walk-node-1:
  STOPPED (switched off; not drift); its pinned build
  ami-04bb9df333af05e5b, mounts and registration all still stand
  and are simply not readable while it is off`, then `no drift:
  meta-state agrees with reality`. A note, not drift, and the
  strict query passed.
- **The login proof: the row's.** `login SKIPPED for walk-node-1
  (nothing proved)`; its record says `the machine is STOPPED
  (switched off; not drift); a login needs it running and the power
  state is the operator's`, `skipped: true`.
- **The verify: NOT the row's** (finding F44). The row says `verify
  ...: SKIPPED -- the machine is STOPPED` and "nothing is started
  for a proof". What it printed was `instance walk-node-1
  verified`, and its record is `ok: true` with three checks only a
  running machine can answer (the startup scripts, the booted
  image, `1 mount(s) under /mnt, 1 declared`). It took 53 seconds
  where the same verify on the running machine took 4. The system
  STARTED your machine, verified it, and stopped it again; that is
  what its code says it does (stage 57: a task that needs a running
  machine may start one, for that task alone, and must put it back
  and say so both times), and it skips only on a runtime that
  cannot start machines. The two lines that say so were above the
  four this page let you see.
- **This page's own check missed it.** `describe-instances` said
  `stopped`, as predicted, because the machine had been put back:
  "still stopped afterwards" does not show "never started". The
  machine can say for itself; 14g begins with that line.)

Then on again, and is it the same machine it was?

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
id=$(grep -m1 'instance_id:' meta-state/instance-state.yaml | awk '{print $2}'); echo "$id"    # i-0792ba0408f0e1388
aws ec2 start-instances --instance-ids "$id" --query 'StartingInstances[0].CurrentState.Name' --output text
aws ec2 wait instance-status-ok --instance-ids "$id" && echo "up"
sft ssh walk-node-1 --command 'hostname; findmnt -no SOURCE,TARGET /mnt/data; cat /mnt/data/walk_team/planted-13a; id -nG | tr " " "\n" | grep -c "^walk_team$"; sudo wc -l < /etc/csis/groups/walk_team.members'
just cloud-verify aws-main walk-node-1 2>&1 | tail -3 | cut -c1-200
just state-query --strict 2>&1 | tail -3 | cut -c1-200
```

The `wait` takes two or three minutes. If `sft ssh` cannot reach
the machine straight after it, OPA's agent has not come back yet:
wait a minute and try again. Then five things from the machine: its
hostname, `walk-node-1-002`; the volume, a device and `/mnt/data`;
your planted line from 13a; `1`, you in `walk_team`; `1`, one name
on the member list. A restart is something this walk has not done
before: whether the mount, the group and the list come back by
themselves is a real question, and any of the five that is missing
is a finding.

(DONE 2026-10-09, 10:28 UTC: all five came back. `walk-node-1-002`;
`/dev/nvme1n1 /mnt/data`; `planted on walk-node-1-001 at
2026-10-08T10:26:08Z`; `1`; `1`. Then `instance walk-node-1
verified` and `no drift: meta-state agrees with reality`. The
mount, the group, the member list and the registration with OPA all
survive a stop and a start, and by then the machine had been
through two of each, the first of them the system's own.)

**14g. Record, push, and let `main` see it.** First, how often the
machine has started, which settles finding F44 by sight.

(2026-10-09: this page first asked the machine's journal, `sudo
journalctl --list-boots`, and promised two boots. It listed ONE,
from 10:27:45 UTC to now: your own start. The journal on this
machine keeps only the boot it is in; the launch of 2026-10-08 is
not in it either. The line could never have shown what this page
said it would. The block after it then ran `just record` before
you meant it to, and you cancelled it with Ctrl-C. That was right,
and it leaves one thing to undo: see the second box.)

Two looks that do outlive a restart. The first asks the machine's
cloud-init log, which gains a line at every boot; the second asks
AWS's own audit trail for every stop and start of this instance in
those fifteen minutes. Claude has seen neither on your machine or
account: if one prints nothing, or AWS refuses the second, say so.

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
sft ssh walk-node-1 --command 'sudo grep -h "running .init-local. at" /var/log/cloud-init.log | sed -E "s/^.*running .init-local. at //" | tail -4'
id=$(grep -m1 'instance_id:' meta-state/instance-state.yaml | awk '{print $2}'); echo "$id"    # i-0792ba0408f0e1388
aws cloudtrail lookup-events --lookup-attributes AttributeKey=ResourceName,AttributeValue="$id" --start-time 2026-10-09T10:20:00Z --end-time 2026-10-09T10:35:00Z --query 'Events[].[EventTime,EventName]' --output text | sort
```

If the system started the machine, the first shows a boot near
10:26 UTC and another near 10:27:45, and the second shows FOUR
events where you made two: your stop near 10:25, a `StartInstances`
and a `StopInstances` you did not type, and your start.

Then undo what the cancelled run left. A run writes its entry in
`meta-state/runs.yaml` however it ends, and the one you cancelled
after five seconds wrote `ok: true` (finding F45). The file had no
other change, so putting it back removes exactly that entry:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
git diff --stat -- meta-state/runs.yaml    # 12 insertions: the cancelled run, 2026_10_09t10_33_44_483423
git checkout -- meta-state/runs.yaml
git status --short                         # exactly: M meta-state/login-proofs.yaml and M meta-state/verifications.yaml
```

Then the record, when you mean it, in four boxes, each ending on
the line that has to be read before the next (the rule at the top
of this page). First, what stands to be recorded:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
git status --short
```

Exactly two lines: ` M meta-state/login-proofs.yaml` and ` M
meta-state/verifications.yaml`, the records 14f's proofs wrote. If
it lists anything else, STOP: a file under `cfg/`, `instances/` or
`groups/`, or `meta-state/pins.yaml`, is a provocation that was not
put back, and `meta-state/runs.yaml` is the cancelled run's entry.

The record:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
just record
git status --short
```

Nothing listed: the record committed those two files with its own.
If anything is listed, STOP and paste it.

The push, and `main`:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
git push
git push origin develop:main
run=""
for i in $(seq 12); do
  sleep 5
  run=$(gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  [ -n "$run" ] && break
done
echo "run ${run:-NOT FOUND after 60 seconds}"
[ -n "$run" ] && gh run watch "$run"
echo "perform on main: $(gh run view "$run" --json conclusion,headSha --jq '"\(.conclusion) at \(.headSha[0:7])"')"
```

`perform on main: success at` and a commit. If it says anything but
`success`, or `run NOT FOUND`, STOP and say what it says: the last
box is not for a red run.

CI's own records, taken back:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
git fetch origin && git merge --ff-only origin/main && git push
git status -sb
```

One line, `## develop...origin/develop`, with nothing after the
branch names and no file under it: your `develop` holds what CI
recorded and is level with GitHub.

**Report:** `stage 14 done` with, part by part, what each command
printed (they are cut to a few lines each on purpose), and the
`perform on main:` line. For 14a say `skipped, keys were live` if it
was. Where a part stopped you, say which line, and stop there.

(STAGE 14 DONE 2026-10-09. `perform on main: success at 6bec954`,
all three jobs; its login proof `login: ok`; `no drift` before and
after. The cancelled run's entry is not in the ledger. The walk's
`develop`, `origin/develop` and `origin/main` agree at bd7c3be.

What the failure walk found, held against the daily driver's
section 6:

| Part | The page | Finding |
| --- | --- | --- |
| 14a lapsed keys | symptom and remedy are an SSO profile's; `preflight` greens dead keys | F40 (new), F30 again |
| 14b no `.envrc` | no row for the missing age identity; the OPA row quotes another sentence | F41 (new), F10 again |
| 14c `name: none` | refused as section 3 promises; a traceback, and no row | F42 (new) |
| 14d `--only` beside `--only-runtime` | three clean one-line refusals; no row, none needed | none |
| 14e unreleased pin | the row holds, grace and refusal both; the starter hides the key | F43 (new) |
| 14f machine off | state query and login proof as written; `verify` STARTS the machine | F44 (new) |
| 14g | a cancelled run records `ok: true` | F45 (new) |
| at 13c | `DESTROY NOT WHITELISTED`, the row's | F38, fixed by stage 88 |

Three of this page's own instructions were wrong on the way and
are corrected above: the `stopped` check of 14f could not see a
start that was undone; the journal line of 14g could not list an
earlier boot; and 14g put a record straight under a status that had
to be read first, which is where your rule "a check ends its box"
comes from.)

## Stage 15 -- the GCE leg: a second cloud in the same tree (DAILY_DRIVER 1.4; CONFIGURATION)

Read the daily driver's 1.4 ("GCP, if you use the GCE runtime") and
the operations guide's "GCE cost discipline". By your decision W4 the
leg is walked in THIS repository: the walk tree, made from the AWS
starter, gains a GCE runtime in the project `csis-sandbox`, bakes
its base and its image there, launches one machine that lives only
for its cycle, and proves itself empty again.

Two things were found before a line of it was written, and you have
decided the second:

- **No page says how a tree gains a second cloud** (finding F46). The
  additions below were put together from the two starters and tried
  twice on 2026-10-09. On a copy of the AWS starter with the cloud
  stubbed, the grown tree loaded, validated with no error, and its
  dry run wrote the four new roots (`base-image/packer-gce`,
  `instance-image/packer-gce`, `instance-image/tofu-gce`,
  `storage/gcp-pd`). And the boxes of 15b themselves were run in
  your container against a throwaway copy of the nine files they
  touch (not your tree), and left each file as intended. What has
  NOT been tried is your tree, with its own values, loading and
  reaching Google: that is 15b's steps 4 and 5.
- **The emptiness check will fail, and that is expected** (finding
  F47). `just cloud-empty` counts everything in the project, and the
  reference configuration lives in the same one. Your decision
  (2026-10-09): walk the leg and judge emptiness by hand. So this
  stage writes down what stands in the project BEFORE (15a), and the
  leftover list at the end must be that and nothing else.

**What stands in `csis-sandbox` today** (read by Claude from your
local machine, 2026-10-09; all three are the reference
configuration's, declared and kept on purpose): no instance; the
disk `gce-data` (30 GB, `us-east1-b`); the image
`imgfile-basic-dask-pckr-gce-ans-20260926-064527`; the bucket
`csis-sandbox-86233086783-default-bucket`.

**What this stage costs on GCP, which is your money.** Nothing until
15d. Then, for some minutes each: two small build machines (spot),
one `e2-small` instance, and a 10 GB standard disk; and two images
that the run disposes as it ends, because the runtime is declared
`ephemeral`. Well under a dollar. At the end of every part this page
says what of the walk's stands on GCP, and at the end of the stage
it must be nothing.

| Part | What | State |
| --- | --- | --- |
| 15a | Google credentials in the container; what stands in the project | done 2026-10-09: `gcloud` in the container acts as the runner through the file; the picture before is the reference's three things and no instance |
| 15b | the tree gains its GCE declarations; validate, dry run, a local commit | **NEXT** |
| 15c | CI for a tree of two clouds (the workflow, the bootstrap's GCP section) | written when 15b reports |
| 15d | the cycle: two bakes, a machine launched, verified and torn down | written when 15c reports |
| 15e | the GCE disk's end, and emptiness judged by hand | written when 15d reports |

**15a. Google credentials in the container.** The container has had
`gcloud` since stage 2 and no Google credentials. As you asked at
the start of the walk, nobody logs in inside it: it gets a
credentials FILE, named by the environment (the section "Google
Cloud credentials through the environment" below, way 2). The file
is a copy of your local machine's Application Default Credentials,
which already impersonate the runner service account. It is a
secret: it goes into the container's home, never onto the volume,
and Claude does not open it.

Every box in this stage starts at the left margin, with no list
around it, because several of them write files and a line that
closes such a text must stand at the very start of its line. Copy
each box whole, from its first line to its last.

**Step 1, on your local machine (the host, NOT the container):** is
the file there?

```sh
cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3 2>/dev/null && [ -d packages/base ] && echo "OK: local machine, the system repository, $(pwd)" || echo "STOP: this is the container, or the path is wrong"
ls -l ~/.config/gcloud/application_default_credentials.json
```

One line with a size and a date. If it says `No such file`, STOP and
say so: the daily driver's 1.4 has the command that makes it
(`gcloud auth application-default login
--impersonate-service-account=...`), and this page will write it out
for you.

**Step 2, still on your local machine:** the copy, owned by you in
the container and readable by nobody else:

```sh
cd /Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3 2>/dev/null && [ -d packages/base ] && echo "OK: local machine, the system repository, $(pwd)" || echo "STOP: this is the container, or the path is wrong"
docker cp ~/.config/gcloud/application_default_credentials.json csis-walk:/home/mykel.alvis/gcp-credentials.json
docker exec -u root csis-walk chown mykel.alvis:mykel.alvis /home/mykel.alvis/gcp-credentials.json
docker exec -u root csis-walk chmod 600 /home/mykel.alvis/gcp-credentials.json
docker exec -u mykel.alvis csis-walk ls -l /home/mykel.alvis/gcp-credentials.json
```

The last line must begin `-rw-------` and name `mykel.alvis` twice.
If it does not, STOP.

**Step 3, in the container:** what kind of credentials are they?
This prints two fields of the file and nothing secret:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
jq -r '.type, (.service_account_impersonation_url // "no impersonation")' ~/gcp-credentials.json
```

Two lines: `impersonated_service_account`, and a URL that ends
`csis-runner@csis-sandbox.iam.gserviceaccount.com:generateAccessToken`.
If the first line says `authorized_user`, STOP: the file is you and
not the runner, and the copy has to be made again after an
impersonating login on your local machine.

**Step 4, in the container:** the environment points at the file.
Three lines join `.envrc`; none is a secret:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
cat >> .envrc <<'EOF'
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/gcp-credentials.json
export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE=$HOME/gcp-credentials.json
export GOOGLE_CLOUD_PROJECT=csis-sandbox CLOUDSDK_CORE_PROJECT=csis-sandbox
EOF
direnv allow
git status --short
```

Nothing listed: `.envrc` is ignored by git, and nothing else changed.
If anything is listed, STOP.

**Step 5, in the container:** do the tools see it? Press Enter once
on an empty line first, so direnv loads the new lines:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
echo "$GOOGLE_APPLICATION_CREDENTIALS"; echo "$CLOUDSDK_CORE_PROJECT"
gcloud compute zones describe us-east1-b --format='value(name,status)'
```

`/home/mykel.alvis/gcp-credentials.json`, `csis-sandbox`, and
`us-east1-b UP`. The last line is the `gcloud` command itself acting
as the runner through the file. Claude has not seen `gcloud` take
this kind of file through the environment: if it refuses, STOP and
paste what it says.

**Step 6, in the container:** the picture BEFORE, kept in a file in
your home for the end of the stage. Reading costs nothing:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
{ echo "== instances"; gcloud compute instances list --format='value(name,zone.basename(),status)'; echo "== disks"; gcloud compute disks list --format='value(name,zone.basename(),sizeGb)'; echo "== images"; gcloud compute images list --no-standard-images --format='value(name,family)'; echo "== buckets"; gcloud storage buckets list --format='value(name)'; } 2>&1 | tee ~/gcp-before.txt
```

It should be the three things named at the top of this stage and no
instance. If it shows anything else, STOP and paste it: something
stands in your project that this page does not know.

**Report:** `stage 15a done` with what steps 3, 5 and 6 printed.
Nothing of the walk's stands on GCP after 15a: it only read.

(DONE 2026-10-09. Step 1 was first typed in the container, where
the guard said `STOP` and `ls` said `No such file`; on your local
machine the file was there. The copy stands in the container's home
as `-rw-------`, yours. Step 5 answered what this page did not
know: `gcloud` does take an impersonating credentials file through
`CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE`. Step 6, kept in
`~/gcp-before.txt`: no instance; the disk `gce-data` (`us-east1-b`,
30 GB); the image
`imgfile-basic-dask-pckr-gce-ans-20260926-064527`; the bucket
`csis-sandbox-86233086783-default-bucket`. Exactly the reference
configuration's three things, as Claude read them from your local
machine. That list is what the end of the stage is judged against.)

**15b. The tree gains its GCE declarations.** In the container. Nine
files change. Seven gain an entry at their end, each a list that the
new entry joins; two have one line edited. The names: runtime
`gcp-main`; image builder `packer-gce`; instance builder `tofu-gce`;
storage builder `gcp-pd`; the disk `walk-data` (not `gce-data`: that
name is taken in this project); the machine `walk-gce-1`. Nothing
here applies anything or reaches GitHub.

**Step 1.** The four builders:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
cat >> cfg/executables.yml <<'EOF'
  - name: gcloud
    binary: gcloud
    version: ">=500"             # the Google Cloud SDK's own version
EOF
cat >> cfg/image-builders.yml <<'EOF'
  - name: packer-gce
    type: packer-gce
    runtime: gcp-main            # NOT the default: the default image builder stays packer-ebs
    executable: packer
    required_plugins:
      - name: googlecompute
        source: github.com/hashicorp/googlecompute
        version: ">= 1.0.0"
      - name: ansible
        source: github.com/hashicorp/ansible
        version: ">= 1.0.0"
EOF
cat >> cfg/instance-builders.yml <<'EOF'
  - name: tofu-gce
    type: tofu-gce
    runtime: gcp-main
    executable: open-tofu
    required_plugins:
      - name: google
        source: hashicorp/google
        version: ">= 5.0.0"
EOF
cat >> cfg/storage-builders.yml <<'EOF'
  - name: gcp-pd
    type: tf-gcp-pd              # a zonal persistent disk, single-attach
    runtime: gcp-main
    executable: open-tofu
    size: 10                     # GB
    disk_type: pd-standard
    variables:
      tags:                      # emitted as labels: lower case
        project: walk
EOF
git status --short
```

Exactly four lines, each ` M cfg/...`: `executables.yml`,
`image-builders.yml`, `instance-builders.yml`, `storage-builders.yml`.
If not, STOP.

**Step 2.** The runtime, and the base's second source. The base
`el10` is the same base, baked a second time, from AlmaLinux's own
images on GCE:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
cat >> cfg/runtime-builders.yml <<'EOF'
  - name: gcp-main
    type: gcloud
    aliases: [gcp, google]
    project_id: csis-sandbox
    region: us-east1
    zone: us-east1-b
    description: "GCE runtime for project {{ this.project_id }} in {{ this.zone }}"
    service_account_email: csis-runner@csis-sandbox.iam.gserviceaccount.com
    session_mechanism: iap
    state_configuration: default # the GCE roots keep their state in this tree's own (S3) backend
    default_disk_size: 10
    bake_preemptible: true       # spot build machines; a preempted bake re-runs
    ephemeral: true              # every image baked here is disposed when a run ends well
    default_machine_type: e2-small
    default_image_builder: packer-gce
    tags:                        # emitted as labels: lower case
      project: walk
      environment: development
    networking:
      network: default
      subnets:
        - name: main
          subnet_id: projects/csis-sandbox/regions/us-east1/subnetworks/default
          is_default: true
          public: true
EOF
sed -i 's/^    storage_types: \[ebs\]$/    storage_types: [ebs, pd]/' cfg/os-builders.yml
cat >> cfg/os-builders.yml <<'EOF'
      - name: gce-el10
        image_builder: packer-gce     # the same base, baked a second time, on GCE
        default_machine_type: e2-small
        ssh_username: packer
        owners:
          - almalinux-cloud           # AlmaLinux's public image project (a vendor fact)
        query:
          filters:
            name: "almalinux-10-v*"
EOF
git diff --stat -- cfg/os-builders.yml cfg/runtime-builders.yml
```

`cfg/os-builders.yml | 11 ++++++++++-`, `cfg/runtime-builders.yml |
25` all plus signs, and `2 files changed, 35 insertions(+), 1
deletion(-)`. If it says 34 insertions and no deletion, the `sed`
did not find its line: STOP.

**Step 3.** The image's second bake, the disk and the machine:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
sed -i 's/^      - image_builder: packer-ebs      # one bake per runtime$/&\n      - image_builder: packer-gce/' images/images.yaml
cat >> storages/storages.yaml <<'EOF'
  - name: walk-data
    type: gcp-pd
    runtime: gcp-main
    groups:
      - walk_team
    share_mode: "2770"
    state: active
    availability_zone: us-east1-b     # a persistent disk is zonal
    tags:
      purpose: data
EOF
cat >> instances/instances.yaml <<'EOF'
  - name: walk-gce-1
    image: team-node
    type: tofu-gce
    runtime: gcp-main
    machine_type: e2-small
    ephemeral: true              # launched, verified and torn down inside its cycle
    description: "The GCE leg's machine; exists only for its cycle"
    storages:
      - name: walk-data
        mount_point: /mnt/walk-data
    tags:
      role: node
EOF
git status --short
```

Exactly nine lines, each ` M`: the six under `cfg/` so far, and
`images/images.yaml`, `instances/instances.yaml`,
`storages/storages.yaml`. If `images/images.yaml` is missing from the
list, the `sed` did not find its line: STOP.

**Step 4.** Does the tree load? `validate` now asks Google as well
as AWS, so the keys must be live:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
aws sts get-caller-identity --query Account --output text
just validate 2>&1 | tail -6 | cut -c1-220
```

`Validation successful.` as the last line. Anything else, STOP and
paste it: this is the first time your tree's own values meet these
declarations, and what it says is the finding.

**Step 5.** The dry run, and what it wrote:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
just dry 2>&1 | tail -3 | cut -c1-200
ls -d generated/base-image/packer-gce generated/instance-image/packer-gce generated/instance-image/tofu-gce generated/storage/gcp-pd
```

A line `Run ... completed:` with all six lifecycles, and then the
four directories, each on its own line and none with `No such file`.
If a directory is missing, STOP.

**Step 6.** What the dry run means to do on GCE, read from the
records it wrote:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
grep -n 'walk-gce-1:' -A22 meta-state/launch-params.yaml | grep -E 'hostname|ephemeral|machine_type|session|device|storage:' | cut -c1-90
```

`ephemeral: true`, `hostname: walk-gce-1-001`, `machine_type:
e2-small`, `session: iap`, a device under `/dev/disk/by-id/`, and
`storage: walk-data`.

**Step 7.** A local commit, not pushed. CI cannot reach Google yet,
and a push now would turn it red; 15c is what makes it able to:

```sh
cd /walk/cs-image-system-walk 2>/dev/null && [ -f cfg/_config.yml ] && echo "OK: the container, $(pwd)" || echo "STOP: this is NOT the container"
git add -A && git commit -m "A GCE runtime beside the AWS one: gcp-main, its base, its image, a disk and a machine for one cycle"
git status -sb
```

`## develop...origin/develop [ahead 1]` and no file under it. Do NOT
push.

**Report:** `stage 15b done` with what steps 4, 5 and 6 printed, or
the step that stopped you and what it said. Nothing of the walk's
stands on GCP after 15b: nothing was applied.

## Stage 16 onward -- written when you reach them

These stages depend on what the earlier ones produce (the bootstrap's
interview, the names it prints), so their exact commands are added to
this page as each one comes up. The order, and the page each follows:

| Stage | What | Follows |
| --- | --- | --- |
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
| F33 | a declared instance that was never launched reads, once its image has a build, as `unavailable: instances/<name>: booted image (runtime <r> could not answer)` in every state query: the bake pins the instance, the query asks the cloud for a machine that does not exist, and the words blame the cloud. The records know it was never launched (no generation in the ledger; `launched: false`) | code: hygiene XII item 13 |
| F34 | observation, not yet a finding: a launched machine carries its `Name` and no `csis_config` tag (the images do, since stage 82), so nothing in AWS says which configuration a machine or its security group belongs to; a teardown that reads the account by tag would not find them | to be judged at teardown (stage 17) |
| F35 | nothing proves the workload role's branch pin. The guide's 3.5 ends at "add the branch pin to the role" and offers no check; the probe authenticates to the CONNECTION and passes the role only as a hint, so it says `accepted ... and issued one` from any branch, pinned or not (seen 2026-10-08: `success` on `develop` with the pin read back from OPA). A team cannot tell a pin that holds from one that does not | words and code: hygiene XII item 14 |
| F36 | a user's `name` is declared as an `ENC[age:...]` marker in `groups/` and committed in CLEAR by the run: `meta-state/identity.yaml`, the identity roots' HCL (the roster lists, resource names, the local part of the mail address), and the login proofs. In a public configuration repository a person's username is public from the first identity run and stays in the history; only the mail domain is protected. The marker suggests otherwise, and nothing in the guide or the starter says so | words, and a decision: hygiene XII item 15 |
| F37 | beside Okta, a member whose account name on a machine differs from their OPA username logs in and never joins the group. OPA makes the account under the user's `unix_user_name` attribute; the login hook matches the account against the member list name for name; the list was written in OPA usernames. Seen when the walk's second person logged in: on the list, not in the group. The reference configuration is exposed the same way | code: stage 87, released in 0.1.1.dev20 |
| F38 | removing a member the way the pages describe FAILS, and they do not say it will. The daily driver (3.1; section 4, "Who may log in") and the operations guide ("Drop a membership") say that for a removal OPA still holds "the plan shows the destroy and the gate sees it". The gate refuses it: `DESTROY NOT WHITELISTED`, exit 3, the run FAILED, by the design rule "membership removals only by explicit decision". The procedure that works, remove the person in the OPA console first and let the next run prune its state, is written nowhere as a procedure, and the refusal does not name it. The operator, on reading it: the rule was a mistake; the system adds members and must be able to remove them | code: stage 88 (20206e8, was hygiene XII item 16), released in 0.1.1.dev21 and PROVED live by 13d (2026-10-09: added by a run, removed by a run, OPA holding nobody afterwards). Words: the daily driver's 3.1 and section 4, the operations guide's "The apply gate", "Drop a membership" and "Identity", and the design where it states the old rule; and a caution the pages do not yet carry: an edit that empties a roster by mistake now removes people, a dry run cannot show it, and the applying run's prune step and plan name each person first |
| F39 | an applying identity run's log shows the group root's plan twice, and the first is not the one applied. The run plans the root once as it writes it (a preview: not saved, not refreshed, read by nothing) and once in the runner, after the prune step. For a membership already gone from OPA the preview says `1 to destroy`, the prune step then takes the attachment out of state, and the runner's plan says `No changes`: a reader of the log meets a destroy that never happens (seen 2026-10-08, 13c). The operations guide says it in one clause under "Drop a membership"; the daily driver's 3.1 and its row "Who may log in" do not say there are two plans or which one counts | words |
| F40 | `just preflight` says `every session present` over keys that have lapsed. For a profile that is not an SSO profile it can read no expiry (`profile 'noaa' is not an SSO profile (no expiry readable)`), counts the session as present, and closes in green; it makes no cloud call, by design. The next command that reaches AWS then fails with `RequestExpired` under a traceback (F30). Seen 2026-10-09 (14a), provoked on purpose. A team working from pasted keys gets a green line that means "not judged", and the daily driver's expired-session row gives it neither the symptom nor the remedy (fresh keys, not `aws sso login`) | words and code: hygiene XII item 17 |
| F41 | the first thing an unsourced shell meets has no row. In a tree that holds any encrypted value (every starter's does), a shell that never loaded `.envrc` stops at `MissingIdentityError: <tree>/cfg: user_builders[0].email_domain: an encrypted value is present but CSIS_CONFIG_IDENTITY is not set -- export the age identity (...)`, under a traceback, before anything is asked of OPA or AWS (seen 2026-10-09, 14b, provoked on purpose). Section 6's table has rows for the OPA pair and for a 401, none for this; 1.7 names the variable but not the symptom | words (and the traceback, with F10's and F30's) |
| F42 | a reserved name is refused correctly and section 6 does not know the refusal. `name: none` on an instance stops `validate` with `ReservedNameError: <file>: instances[0].name: a name may not be 'none'` and the reason, exactly as section 3 promises (file, entry, word). But it comes under a traceback, not as a line under `Validation failed with N error(s)`, which is the only form section 6's table gives a rule that failed before anything was generated; and the table has no row for it (seen 2026-10-09, 14c, provoked on purpose) | words (and the traceback, with F10's, F30's and F41's) |
| F43 | the starter does not show the keys the page tells a team to settle. The daily driver's 1.9 (step 3) lists `require_released_builds`, `require_image_tests` and `preflight.expected_run_minutes` among `cfg/_config.yml`'s decisions; the `standard-aws` starter's file carries none of them, not even as a comment, and its image declares no `release:`. So section 6's row for an unreleased pin cannot happen in a starter tree until someone adds a key the tree never mentions, and once it is on, the grace's own advice (`verify it, then release it`) has no declared release to make. Seen 2026-10-09 (14e): the walk had to write the key in by hand to reach the row, which then behaved exactly as written | words and the starters: hygiene XII item 18 |
| F44 | `verify` does not skip a machine that is switched off: it STARTS it, verifies it and stops it again. Section 6's row gives `verify ...: SKIPPED -- the machine is STOPPED` and says "nothing is started for a proof". On AWS, with `walk-node-1` stopped by its operator, `just cloud-verify` printed `instance walk-node-1 verified` and recorded `ok: true` with three checks only a running machine can answer, in 53 seconds against 4 on the running machine; the login proof straight after was `SKIPPED`, and the machine was `stopped` again when looked at (seen 2026-10-09, 14f). The code does this on purpose (stage 57: a bounded task that needs a running machine may start one and must put it back, saying so both times) and skips only where the runtime cannot start machines. So the row is wrong for one of its two proofs, the two proofs differ and no page says so, and an operator who switched a machine off to save money is not told that verifying it boots it | words; and a question for the operator: which of the two is the mistake, the page or the start |
| F45 | a run its operator cancels is journalled as a success. `just record` was interrupted with Ctrl-C five seconds in, before anything was generated, and `meta-state/runs.yaml` gained an entry for it: `ok: true`, `error: null`, `apply: {}` (seen 2026-10-09, 14g; run 2026_10_09t10_33_44_483423). The run writes its entry on the way out however it ends, and an interrupt sets no error. Nothing was committed, so the entry was removed by restoring the file; left alone, the next record would have committed it, and the ledger would say a run that never ran was good | code: hygiene XII item 19 |
| F46 | no page says how a tree gains a second cloud. The walk's GCE leg adds a GCE runtime to a tree made from `standard-aws` (decision W4). The daily driver's 1.9 offers a starter per cloud and `complete` for both; CONFIGURATION describes each declaration; nothing says which ten declarations a second cloud needs (an executable, an image builder, an instance builder, a source for the base on the new runtime, a storage builder, the runtime, the image's second bake, a storage, an instance), nor that the tree's CI workflow is its starter's and has to be changed for `complete`'s (`init-config --from complete`), nor that the terraform modules for both clouds are already in every tree. Found 2026-10-09, writing stage 15 | words |
| F47 | two configurations in one GCP project cannot both prove a runtime empty. `cloud-empty` (and so the end of every `cloud-cycle`) counts every instance and disk in the zone, every custom image and every bucket in the PROJECT, less this tree's own declared storages and released builds. The reference configuration keeps a disk and a bucket standing in `csis-sandbox`, so the walk's cycle there must end in a failing emptiness check that names them, and the reference's would name the walk's. Stage 82 gave IMAGES a label that says whose they are; instances, disks and buckets carry none. Found 2026-10-09 by reading, before anything was spent; the operator's decision: walk the leg and judge emptiness by hand | code: hygiene XII item 20 |
| F25 | an applying run's log can lose the one line that says what was applied: it keeps the last 40 lines of a command's output, and tofu prints `Apply complete! Resources: ...` BEFORE the root's outputs, so a root with 37 or more lines of outputs (the reference's identity root: 40) shows only outputs | code: hygiene XII item 8 |
