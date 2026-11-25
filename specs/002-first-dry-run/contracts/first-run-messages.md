# Contract: the first-run failures, one line each

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R12

For each condition of FR-013, the command that fails and its line. A
line marked **today** is the system's already; one marked **new** is
this feature's.

| Condition | Command that fails | The line |
| --- | --- | --- |
| uv absent | box 1, `uv tool install ...` | the shell's own, for example `zsh: command not found: uv`; the prerequisites table above the box says where uv comes from (**today**; no command of the system can run without uv) |
| docker, tofu, packer or bash absent | box 2, `validate` | `<tool>: binary '<binary>' not found (declared in cfg/executables.yml; an absolute path, or a name on PATH) -- install it (where each tool comes from: the daily driver, section 1.2)` (**new**: the remedy after the dash) |
| a tool older than its floor | box 2, `validate` | `<tool> <found> does not meet its requirement <needed> (cfg/executables.yml)` (**today**) |
| the daemon does not answer | box 3, `run --all` | `docker runtime docker-main: the daemon at <where> cannot be reached (<the CLI's first line>) (the runtime's daemon must answer \`docker version\` from this machine: start it (OrbStack, Docker Desktop, the engine on the host), or fix the runtime's \`host\` / \`context\`; \`preflight\` says which)` (**new**: the current CLI's wording recognised; the remedy on a run's failure as on a load's) |
| installed without the provider | box 2, `validate` | `runtime type 'docker' ...: install the extra: uv tool install --python 3.13 --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match 'cs-image-system[docker]==<the installed release>'` (**new** 2026-11-25: the umbrella's table gave the unpinned install, which until 1.0 takes PyPI's older release; the exact command is the one install form at the release installed) |
| an older release installed | none | box 1's exact pin, with `--upgrade`, ends on the page's release; the box's last line prints it (**new** by the page, no code; that a pinned install replaces an older one is confirmed at implementation, research R4) |
| a configuration already in `csis-quickstart` | box 2, `init-config` | a directory that is not a configuration: the refusal of today, one line. A tree this release did not write: the `REFUSED <file>` lines of today, then `init-config: <dest> already holds a configuration this release did not write; to start over remove it, or keep it and refresh the release's files with --force` (**new**, the closing line). The quickstart's own tree from the same release: no failure (story 1 scenario 5) |

Every new line is one line, carries its cause first and its remedy
after, and exits as the command exits today (`validate` 1, a failed run
1, `init-config` 1 on a refusal and 2 on a directory it will not write
into).

The tests for the new lines are behaviour tests of the commands: a
missing binary, a docker CLI answering with the current wording, a
refused refresh. None asserts a document.
