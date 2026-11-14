# Changes: the stage index

One line per landed stage and per release, newest first, read from the
squash commits on `develop` by the command below: a subject that starts
with "Stage N", "release" or "Hygiene <numeral>", or names "(stage N …)"
or "(hygiene <numeral> …)" in parentheses. Appended by the release from
then on. This page and [INCIDENTS.md](INCIDENTS.md) are the two current
pages that carry dates and stage numbers by design, so that no other
page has to.

```sh
git log --first-parent develop --format='%h|%ad|%s' --date=short
```

The public history starts on 2026-09-16 with stage 37; the stages before
it landed in the private repository the public one was cut from, and
their record is the frozen [history/PLAN.md](history/PLAN.md) and
[history/LEDGER.md](history/LEDGER.md). A few early public stages have
squash subjects that name no number and so have no row. "Released in"
names the first release whose tag contains the squash; a development
release counts. The newest row of each stage carries an anchor
(`#s<stage>`, `#h<bundle>`, `#r<version>` with dots as dashes; a bundle
that is also a numbered stage carries both) so that a page can point at
the entry without naming the number in its text.

| Stage | Landed | Released in | Squash subject |
| --- | --- | --- | --- |
| <a id="r0-1-9"></a>release 0.1.9 | 2026-11-14 | 0.1.9 | release 0.1.9 |
| <a id="s112"></a>§112 | 2026-11-13 | 0.1.9 | Stage 112: a release in two boxes |
| <a id="hxxvii"></a><a id="s134"></a>§134 | 2026-11-13 | 0.1.9 | Stage 134: hygiene bundle XXVII, parents right at every moment |
| <a id="r0-1-8"></a>release 0.1.8 | 2026-11-12 | 0.1.8 | release 0.1.8 |
| <a id="hxxvi"></a><a id="s133"></a>§133 | 2026-11-12 | 0.1.8 | Stage 133: hygiene bundle XXVI, per-run draws and the rule's reach |
| <a id="hxxv"></a><a id="s132"></a>§132 | 2026-11-12 | 0.1.8 | Stage 132: hygiene bundle XXV, one run per context and the pinned record |
| <a id="r0-1-7"></a>release 0.1.7 | 2026-11-12 | 0.1.7 | release 0.1.7 |
| <a id="hxxiv"></a><a id="s130"></a>§130 | 2026-11-07 | 0.1.7 | Stage 130: hygiene bundle XXIV, the lint bar and the small findings |
| <a id="s129"></a>§129 | 2026-11-07 | 0.1.7 | Stage 129: the sources stop narrating |
| <a id="s128"></a>§128 | 2026-11-07 | 0.1.7 | Stage 128: tests named for behaviour |
| <a id="s127"></a>§127 | 2026-11-06 | 0.1.7 | Stage 127: loading once, without the cloud |
| <a id="s126"></a>§126 | 2026-11-06 | 0.1.7 | Stage 126: the package shape |
| <a id="s131"></a>§131 | 2026-11-06 | 0.1.7 | Stage 131: registrations carry their plugin's namespace |
| <a id="s125"></a>§125 | 2026-11-05 | 0.1.7 | Stage 125: the contract's surface, its services and its version |
| <a id="s124"></a>§124 | 2026-11-05 | 0.1.7 | Stage 124: the run context and the engine part ways |
| <a id="s123"></a>§123 | 2026-11-05 | 0.1.7 | Stage 123: hashicorp-utils stops reaching back |
| <a id="s122"></a>§122 | 2026-11-05 | 0.1.7 | Stage 122: storage and identity leave the core |
| <a id="s121"></a>§121 | 2026-11-05 | 0.1.7 | Stage 121: the core names no runtime |
| <a id="s120"></a>§120 | 2026-11-04 | 0.1.7 | Stage 120: a provider-neutral terraform root |
| <a id="s119"></a>§119 | 2026-11-04 | 0.1.7 | Stage 119: the stage index and the end of narration |
| <a id="s118"></a>§118 | 2026-11-04 | 0.1.7 | Stage 118: the summary layer comes current |
| <a id="r0-1-7-dev1"></a>release 0.1.7.dev1 | 2026-11-02 | 0.1.7.dev1 | release 0.1.7.dev1 |
| <a id="s111"></a>§111 | 2026-11-02 | 0.1.7.dev1 | Stage 111: hygiene bundle XXIII, a lapsed SSO token is judged |
| <a id="s110"></a>§110 | 2026-11-02 | 0.1.7.dev1 | Stage 110: hygiene bundle XXII, the take gap |
| <a id="r0-1-6"></a>release 0.1.6 | 2026-11-02 | 0.1.6 | release 0.1.6 |
| <a id="r0-1-6-dev2"></a>release 0.1.6.dev2 | 2026-11-01 | 0.1.6.dev2 | release 0.1.6.dev2 |
| <a id="s108"></a>§108 | 2026-11-01 | 0.1.6 | Stage 108: hygiene bundle XXI |
| <a id="s109"></a>§109 | 2026-11-01 | 0.1.6 | Stage 109: Podman Desktop in the test cycle |
| <a id="s103"></a>§103 | 2026-11-01 | 0.1.6 | Stage 103, branch 3: the bootstrap, the docker starter, the docs |
| §103 | 2026-11-01 | 0.1.6 | Stage 103, branch 2: containers and volumes on the docker runtime |
| §103 | 2026-10-31 | 0.1.6 | Stage 103, branch 1: the docker runtime and its bake |
| <a id="s105"></a>§105 | 2026-10-31 | 0.1.6 | Stage 105: a declared output image name |
| <a id="r0-1-6-dev1"></a>release 0.1.6.dev1 | 2026-10-31 | 0.1.6.dev1 | release 0.1.6.dev1 |
| <a id="s107"></a>§107 | 2026-10-31 | 0.1.6 | Stage 107: releases are cut on main |
| <a id="r0-1-5"></a>release 0.1.5 | 2026-10-31 | 0.1.5 | release 0.1.5 |
| <a id="hxx"></a><a id="s104"></a>hygiene XX (§104) | 2026-10-31 | 0.1.5 | Hygiene XX: the bootstrap covers every declared state manager and says what it leaves |
| <a id="s106"></a>§106 | 2026-10-30 | 0.1.5 | Stage 106: the image-source catalog in the system's query vocabulary |
| <a id="r0-1-4"></a>release 0.1.4 | 2026-10-29 | 0.1.4 | release 0.1.4 |
| <a id="hxix"></a><a id="s102"></a>hygiene XIX (§102) | 2026-10-29 | 0.1.4 | Hygiene XIX: pyright's override check is on, and the okta builder tests stand alone |
| <a id="s30"></a>§30 | 2026-10-29 | 0.1.4 | Stage 30, branch 2: the proof plugin, a state backend against the contract alone |
| §30 | 2026-10-29 | 0.1.4 | Stage 30, branch 1: the plugin contract is a package of protocols |
| <a id="hxviii"></a><a id="s101"></a>hygiene XVIII (§101) | 2026-10-28 | 0.1.4 | Hygiene XVIII: the CLI takes --version, so a starter's init names its release |
| <a id="r0-1-3"></a>release 0.1.3 | 2026-10-28 | 0.1.3 | release 0.1.3 |
| <a id="hxvii"></a><a id="s100"></a>hygiene XVII (§100) | 2026-10-28 | 0.1.3 | Hygiene XVII: CI's guard passes a vendor image move alone |
| <a id="hxvi"></a><a id="s98"></a>hygiene XVI (§98) | 2026-10-27 | 0.1.3 | Hygiene XVI: config-drift talks and travels light; starters skip unset |
| <a id="r0-1-2"></a>release 0.1.2 | 2026-10-27 | 0.1.2 | release 0.1.2 |
| <a id="r0-1-2-dev2"></a>release 0.1.2.dev2 | 2026-10-26 | 0.1.2.dev2 | release 0.1.2.dev2 |
| <a id="s99"></a>§99 | 2026-10-26 | 0.1.2 | A development pin installs from TestPyPI again (stage 99) |
| <a id="r0-1-2-dev1"></a>release 0.1.2.dev1 | 2026-10-26 | 0.1.2.dev1 | release 0.1.2.dev1 |
| <a id="hxv"></a><a id="s97"></a>hygiene XV (§97) | 2026-10-24 | 0.1.2 | Hygiene XV: a tree init-config writes links out at the release's tag |
| <a id="s66"></a>§66 | 2026-10-24 | 0.1.2 | Starter repositories a team can use from GitHub (stage 66) |
| <a id="hxiv"></a><a id="s96"></a>hygiene XIV (§96) | 2026-10-23 | 0.1.2 | Hygiene XIV: a release resumes, and the state query reads groups back |
| <a id="r0-1-1"></a>release 0.1.1 | 2026-10-23 | 0.1.1 | release 0.1.1 |
| <a id="s83"></a>§83 | 2026-10-17 | 0.1.1 | A release asks its publish target before it starts (stage 83) |
| <a id="hxiii"></a><a id="s95"></a>hygiene XIII (§95) | 2026-10-17 | 0.1.1 | Hygiene XIII: cloud-upgrade records; init-config refuses a stale install |
| <a id="r0-1-1-dev26"></a>release 0.1.1.dev26 | 2026-10-16 | 0.1.1.dev26 | release 0.1.1.dev26 |
| <a id="s92"></a>§92 | 2026-10-16 | 0.1.1 | The runner image carries the docker connection the modification tests use (stage 92, .4) |
| §92 | 2026-10-16 | 0.1.1 | Every job's permissions block reads packages, for the image's pull (stage 92) |
| §92 | 2026-10-16 | 0.1.1 | The runner image carries node for pyright (stage 92, alma10-20261016.3) |
| §92 | 2026-10-16 | 0.1.1 | The runner image trusts the job's checkout (stage 92, alma10-20261016.2) |
| §92 | 2026-10-16 | 0.1.1 | CI runs inside an AlmaLinux 10 image of the system's own, described once for any CI (stage 92) |
| <a id="s93"></a>§93 | 2026-10-16 | 0.1.1 | Everything the system makes carries its configuration's id (stage 93) |
| <a id="hxii"></a><a id="s81"></a>hygiene XII (§81) | 2026-10-14 | 0.1.1 | The write role reads as the read role does (hygiene XII, item 33) |
| <a id="r0-1-1-dev25"></a>release 0.1.1.dev25 | 2026-10-14 | 0.1.1.dev25 | release 0.1.1.dev25 |
| hygiene XII (§81) | 2026-10-14 | 0.1.1 | The operator's three decisions of 2026-10-14 (hygiene XII, 5/15/21) |
| hygiene XII (§81) | 2026-10-14 | 0.1.1 | The probe judges the role, and GCE's mount check can fail (hygiene XII, 14/22) |
| hygiene XII (§81) | 2026-10-14 | 0.1.1 | What a failure says: one line, never a traceback (hygiene XII, 17/26) |
| hygiene XII (§81) | 2026-10-14 | 0.1.1 | A shared account is granted nothing by default (hygiene XII, item 23) |
| hygiene XII (§81) | 2026-10-14 | 0.1.1 | Teardown finds nothing left behind, on either cloud (hygiene XII, 9/31/32) |
| hygiene XII (§81) | 2026-10-14 | 0.1.1 | Hygiene XII, the records' noise (items 8, 13, 19, 24, 27, 30) |
| hygiene XII (§81) | 2026-10-14 | 0.1.1 | Hygiene XII, the starters and init-config (items 1, 2, 6, 12, 18, 29) |
| <a id="s65"></a>§65 | 2026-10-14 | 0.1.1 | Walking the daily driver from nothing, and what it found (stage 65) |
| <a id="r0-1-1-dev24"></a>release 0.1.1.dev24 | 2026-10-14 | 0.1.1.dev24 | release 0.1.1.dev24 |
| <a id="s91"></a>§91 | 2026-10-14 | 0.1.1 | CI names the machine it runs on and the actions it uses (stage 91) |
| <a id="r0-1-1-dev23"></a>release 0.1.1.dev23 | 2026-10-13 | 0.1.1.dev23 | release 0.1.1.dev23 |
| <a id="s90"></a>§90 | 2026-10-13 | 0.1.1 | A group's release is decided by the state, not by a record (stage 90) |
| <a id="r0-1-1-dev22"></a>release 0.1.1.dev22 | 2026-10-13 | 0.1.1.dev22 | release 0.1.1.dev22 |
| <a id="s89"></a>§89 | 2026-10-13 | 0.1.1 | CI makes the login proof while it holds the write identity (stage 89) |
| <a id="r0-1-1-dev21"></a>release 0.1.1.dev21 | 2026-10-08 | 0.1.1.dev21 | release 0.1.1.dev21 |
| <a id="s88"></a>§88 | 2026-10-08 | 0.1.1 | A membership the YAML dropped is removed by the run (stage 88) |
| <a id="r0-1-1-dev20"></a>release 0.1.1.dev20 | 2026-10-08 | 0.1.1.dev20 | release 0.1.1.dev20 |
| <a id="s87"></a>§87 | 2026-10-08 | 0.1.1 | A group on a machine lists its members by account name (stage 87) |
| <a id="r0-1-1-dev19"></a>release 0.1.1.dev19 | 2026-10-07 | 0.1.1.dev19 | release 0.1.1.dev19 |
| <a id="s86"></a>§86 | 2026-10-07 | 0.1.1 | A bake waits for the package database (stage 86) |
| <a id="r0-1-1-dev17"></a>release 0.1.1.dev17 | 2026-10-07 | 0.1.1.dev17 | release 0.1.1.dev17 |
| <a id="s85"></a>§85 | 2026-10-07 | 0.1.1 | The first identity apply of a new tree has nothing to prune (stage 85) |
| <a id="r0-1-1-dev16"></a>release 0.1.1.dev16 | 2026-10-07 | 0.1.1.dev16 | release 0.1.1.dev16 |
| <a id="s84"></a>§84 | 2026-10-07 | 0.1.1 | Stage 84: a new group can be created -- the gid lookup waits for its group |
| <a id="r0-1-1-dev15"></a>release 0.1.1.dev15 | 2026-10-06 | 0.1.1.dev15 | release 0.1.1.dev15 |
| <a id="s82"></a>§82 | 2026-10-05 | 0.1.1 | Stage 82: an image says which configuration owns it (with hygiene XII 3-4) |
| §65 | 2026-10-05 | 0.1.1 | Stage 65: the operator's decisions W1-W6 |
| §65 | 2026-10-05 | 0.1.1 | Stage 65 refreshed: the walk after stages 70 to 80 |
| <a id="s80"></a>§80 | 2026-10-05 | 0.1.1 | Stage 80 landed: section removed, preamble current |
| §80 | 2026-10-05 | 0.1.1 | Stage 80: hygiene bundle XI -- the reference tree bakes on a t3.medium |
| <a id="s75"></a>§75 | 2026-10-05 | 0.1.1 | Stage 75 landed: section removed, preamble current |
| §75 | 2026-10-05 | 0.1.1 | Stage 75: the second perform failed on cloudflow's EL8 parent |
| <a id="r0-1-1-dev14"></a>release 0.1.1.dev14 | 2026-10-04 | 0.1.1.dev14 | release 0.1.1.dev14 |
| <a id="s78"></a>§78 | 2026-10-04 | 0.1.1 | Stage 78 landed: section removed, preamble current |
| §78 | 2026-10-04 | 0.1.1 | Stage 78: the documentation states stages 75 and 79 |
| <a id="s79"></a>§79 | 2026-10-04 | 0.1.1 | Stage 79 landed: section removed, preamble current |
| §79 | 2026-10-04 | 0.1.1 | Stage 79: hygiene bundle X -- narrow scoped bakes, keep completed builds |
| §75 | 2026-10-04 | 0.1.1 | Stage 75: step 9 done -- the standalone posix proof logged in over ssh |
| §75 | 2026-10-04 | 0.1.1 | Stage 75: step 8 done on coops-model-005; perform waits for main |
| <a id="r0-1-1-dev13"></a>release 0.1.1.dev13 | 2026-10-04 | 0.1.1.dev13 | release 0.1.1.dev13 |
| §75 | 2026-10-04 | 0.1.1 | Stage 75: steps 1-7 and 10 merged; steps 8-9 wait for a release |
| §75 | 2026-10-04 | 0.1.1 | Stage 75 (steps 1-7, 10): a POSIX identity plugin, alone and beside Okta |
| <a id="s77"></a>§77 | 2026-10-03 | 0.1.1 | Stage 77 landed: section removed, preamble current |
| §77 | 2026-10-03 | 0.1.1 | Stage 77: the documentation states the reserved-name rules of stage 76 |
| <a id="r0-1-1-dev12"></a>release 0.1.1.dev12 | 2026-10-03 | 0.1.1.dev12 | release 0.1.1.dev12 |
| <a id="s76"></a>§76 | 2026-10-03 | 0.1.1 | Stage 76 landed: section removed, preamble current |
| §76 | 2026-10-03 | 0.1.1 | Stage 76: `none` is a reserved name, and the reserved-name rule is tested |
| §76 | 2026-10-03 | 0.1.1 | Stage 76: INVALID_CONFIG_KEYS is a different check and is left alone |
| §76 | 2026-10-03 | 0.1.1 | Stage 76: the reserved names are decided; none as a value is explicit |
| §76 | 2026-10-03 | 0.1.1 | Stage 76 planned: none is a reserved name, and the rule gets tests |
| §75 | 2026-10-03 | 0.1.1 | Stage 75: `posix: none` is a valid choice; none names no resource |
| §75 | 2026-10-03 | 0.1.1 | Stage 75: repair step 5's first sentence |
| §75 | 2026-10-03 | 0.1.1 | Stage 75: posix is required on the okta-tf group builder, none excluded |
| §75 | 2026-10-03 | 0.1.1 | Stage 75 planned: a POSIX identity plugin, alone and beside Okta |
| §65 | 2026-10-02 | 0.1.1 | Stage 65: the walk's plan refreshed after stage 70 |
| <a id="r0-1-1-dev11"></a>release 0.1.1.dev11 | 2026-10-02 | 0.1.1.dev11 | release 0.1.1.dev11 |
| <a id="s70"></a>§70 | 2026-10-02 | 0.1.1 | Stage 70 landed: section removed, its standing mandate kept |
| §70 | 2026-10-02 | 0.1.1 | Stage 70 step 6: the Okta and OPA section of the bootstrap; stage 70 landed |
| §70 | 2026-10-02 | 0.1.1 | Stage 70 step 6: the Okta section's decisions and plan |
| <a id="r0-1-1-dev10"></a>release 0.1.1.dev10 | 2026-10-02 | 0.1.1.dev10 | release 0.1.1.dev10 |
| <a id="hix"></a>hygiene IX | 2026-10-02 | 0.1.1 | Hygiene bundle IX landed whole: section removed |
| hygiene IX | 2026-10-02 | 0.1.1 | Hygiene bundle IX: init-config keeps a tree's values, the bootstrap names its credentials, the ruleset needs no bypass |
| hygiene IX | 2026-10-02 | 0.1.1 | Hygiene IX item 3: the ruleset's Actions-app bypass is refused by GitHub, and unneeded |
| hygiene IX | 2026-10-02 | 0.1.1 | Hygiene IX item 2: the apply's credentials appear only in the generated README |
| <a id="r0-1-1-dev9"></a>release 0.1.1.dev9 | 2026-10-02 | 0.1.1.dev9 | release 0.1.1.dev9 |
| §70 | 2026-10-02 | 0.1.1 | Stage 70 step 5: the GCP section of the bootstrap |
| <a id="r0-1-1-dev8"></a>release 0.1.1.dev8 | 2026-10-01 | 0.1.1.dev8 | release 0.1.1.dev8 |
| §70 | 2026-10-01 | 0.1.1 | Stage 70 step 4: the AWS section of the bootstrap |
| hygiene IX | 2026-10-01 | 0.1.1 | Hygiene bundle IX opened: init-config --force overwrites a team's workflow values |
| <a id="r0-1-1-dev7"></a>release 0.1.1.dev7 | 2026-10-01 | 0.1.1.dev7 | release 0.1.1.dev7 |
| §70 | 2026-10-01 | 0.1.1 | Stage 70, iteration one: the bootstrap -- the framework and the GitHub section |
| <a id="r0-1-1-dev6"></a>release 0.1.1.dev6 | 2026-10-01 | 0.1.1.dev6 | release 0.1.1.dev6 |
| <a id="s74"></a>§74 | 2026-10-01 | 0.1.1 | Stage 74: the documentation stage for hygiene VIII, stage 72 and stage 73 |
| <a id="hviii"></a>hygiene VIII | 2026-10-01 | 0.1.1 | Hygiene bundle VIII landed whole: section removed, documentation stage updated |
| hygiene VIII | 2026-10-01 | 0.1.1 | Hygiene VIII items 3-5: the log says what commands said, an applying script is not drift, a lost draw goes back |
| <a id="s73"></a>§73 | 2026-10-01 | 0.1.1 | Stage 73 landed: the coops model replaced onto a different EFS share |
| hygiene VIII | 2026-10-01 | 0.1.1 | Hygiene VIII item 5: an alias draw survives a run that recorded nothing |
| <a id="s72"></a>§72 | 2026-09-30 | 0.1.1 | Stage 72 landed: the coops model resized in place, then by replacement |
| §72 | 2026-09-30 | 0.1.1 | Stage 72 Part B done: the replacement, the EFS data kept |
| §72 | 2026-09-30 | 0.1.1 | Stage 72 Part A closed: the perform job on main is green at ecee611 |
| hygiene VIII | 2026-09-30 | 0.1.1 | Hygiene VIII item 4: an applying run's committed script fails config-drift |
| §72 | 2026-09-30 | 0.1.1 | Stage 72: the second resize, and Part B / stage 73 read t3.medium |
| §72 | 2026-09-30 | 0.1.1 | Stage 72 Part A done: the in-place resize, proved live |
| <a id="r0-1-1-dev5"></a>release 0.1.1.dev5 | 2026-09-30 | 0.1.1.dev5 | release 0.1.1.dev5 |
| hygiene VIII | 2026-09-30 | 0.1.1 | Hygiene VIII item 2: the machine type is a launch parameter, resized in place |
| §73 | 2026-09-30 | 0.1.1 | Stage 73: plan the coops model's replacement onto a different EFS share |
| §72 | 2026-09-30 | 0.1.1 | Stage 72: split the resize into in place, then by replacement |
| §72 | 2026-09-30 | 0.1.1 | Stage 72: plan the coops model's resize by replacement |
| <a id="r0-1-1-dev4"></a>release 0.1.1.dev4 | 2026-09-29 | 0.1.1.dev4 | release 0.1.1.dev4 |
| <a id="s71"></a>§71 | 2026-09-29 | 0.1.1 | Stage 71, hygiene bundle VIII, item 1: as the workload, the login proof's client is handed the team and the address |
| <a id="r0-1-1-dev3"></a>release 0.1.1.dev3 | 2026-09-29 | 0.1.1.dev3 | release 0.1.1.dev3 |
| <a id="s68"></a>§68 | 2026-09-29 | 0.1.1 | Stage 68, hygiene bundle VII, item 2: the run's callbacks find the command; the bundle lands whole |
| §68 | 2026-09-29 | 0.1.1 | Stage 68, hygiene bundle VII, item 1: the fixture's Debian builder moves to bookworm |
| §68 | 2026-09-29 | 0.1.1 | Stage 68, hygiene bundle VII, items 3 and 4: the starter workflow's identity step and the client's environment |
| <a id="hvii"></a>hygiene VII | 2026-09-28 | 0.1.1 | Hygiene VII item 2: the starter Justfile's CSIS override does not reach the callbacks |
| <a id="s69"></a>§69 | 2026-09-28 | 0.1.1 | Stage 69: CI from scratch, the guide every starter tree carries |
| §70 | 2026-09-28 | 0.1.1 | Stage 70: plan the bootstrap and record the operator's eight decisions |
| <a id="r0-1-1-dev2"></a>release 0.1.1.dev2 | 2026-09-26 | 0.1.1.dev2 | release 0.1.1.dev2 |
| <a id="s64"></a>§64 | 2026-09-26 | 0.1.1 | Stage 64: the release is the whole system; the reference configuration stands alone |
| <a id="s67"></a>§67 | 2026-09-26 | 0.1.1 | Stage 67, hygiene bundle VI, item 2: eight remnants of the dead-field list |
| §67 | 2026-09-26 | 0.1.1 | Stage 67 item 1: a child's fingerprint carries its parent's fingerprint, never a build id |
| §67 | 2026-09-26 | 0.1.1 | Stage 67: record the operator's decisions on both items |
| <a id="s63"></a>§63 | 2026-09-26 | 0.1.1 | Stage 63, dead fields and misleading messages: decided field by field, all landed |
| §63 | 2026-09-25 | 0.1.1 | Stage 63: record the operator's decisions on the dead-field list |
| §67 | 2026-09-25 | 0.1.1 | Stage 67 item 1: the operator chose option one |
| §63 | 2026-09-25 | 0.1.1 | Stage 63: record both chains as landed; open hygiene bundle VI (stage 67) |
| §63 | 2026-09-25 | 0.1.1 | Stage 63, chain 22 then 23: one bake-user resolver; the three dead fields live |
| §63 | 2026-09-25 | 0.1.1 | Stage 63, chain 20 then 21: storage zones follow the builder's runtime and the disk's own zone |
| §63 | 2026-09-25 | 0.1.1 | Stage 63: record medium items 14-19 as landed; the chains stay open |
| §63 | 2026-09-25 | 0.1.1 | Stage 63, medium items 14 and 17: the declared gcloud; Filestore in the state query |
| §63 | 2026-09-25 | 0.1.1 | Stage 63, medium items 15, 16, 18, 19: validation at load and builder hooks |
| §63 | 2026-09-25 | 0.1.1 | Stage 63: record the operator's decisions on the chains 20-23 |
| §63 | 2026-09-25 | 0.1.1 | Stage 63: record the operator's decisions on medium items 14-19 |
| §63 | 2026-09-24 | 0.1.1 | Stage 63: record the low-hanging group as landed; medium items and chains stay open |
| §63 | 2026-09-24 | 0.1.1 | Stage 63, low-hanging group: thirteen defects fixed, each with a test |
| §63 | 2026-09-24 | 0.1.1 | Stage 63 ordered for execution: thirteen low-hanging items first, six medium, then the two chains in dependency order |
| §66 | 2026-09-24 | 0.1.1 | Stage 66 planned: three starter repositories, published from docs/examples per release, never edited at the destination |
| §65 | 2026-09-24 | 0.1.1 | Stage 65 planned: walking the daily driver from a fresh repository against a release |
| <a id="s62"></a>§62 | 2026-09-24 | 0.1.1 | Stage 62: the daily driver -- how a team actually uses the system, and every README to one contract |
| <a id="s61"></a>§61 | 2026-09-23 | 0.1.1 | Stage 61: hygiene bundle V -- unaskable groups, the session note, stale attachments, the release grace, the stray tfvars |
| <a id="s59"></a>§59 | 2026-09-22 | 0.1.1 | Stage 59: a pool of names, each spent once |
| <a id="s19"></a>§19 | 2026-09-22 | 0.1.1 | Stage 19: the first real model image, released, in use, and released again |
| <a id="s56"></a>§56 | 2026-09-22 | 0.1.1 | Stage 56: CI logs in through the policy the system manages, and that is the proof |
| <a id="s55"></a>§55 | 2026-09-21 | 0.1.1 | Stage 55 step 4: the canonical name carries the generation |
| <a id="s60"></a>§60 | 2026-09-21 | 0.1.1 | Stage 60: an instance has generations, and each one is a machine |
| <a id="s58"></a>§58 | 2026-09-21 | 0.1.1 | Stage 58: an instance answers to its provider's names too |
| §58 | 2026-09-21 | 0.1.1 | Stage 58 step 1 settled live: the instance id resolves natively, the provider hostname does not |
| §55 | 2026-09-21 | 0.1.1 | Stage 55 steps 1-3: a canonical hostname is claimed once in OPA |
| <a id="s57"></a>§57 | 2026-09-21 | 0.1.1 | Stage 57: the power state belongs to the operator |
| §57 | 2026-09-21 | 0.1.1 | Stage 57: the power-state query is a runtime contract member |
| §57 | 2026-09-21 | 0.1.1 | Stage 57 states the rule: the power state belongs to the operator |
| §57 | 2026-09-21 | 0.1.1 | Stage 57 names the missing primitive: the machine's power state |
| §57 | 2026-09-21 | 0.1.1 | Stage 57: a machine that exists may be switched off |
| §56 | 2026-09-21 | 0.1.1 | Stage 56: CI logs in as a member of the group, and that is the proof |
| §55 | 2026-09-21 | 0.1.1 | Stage 55: a canonical hostname is claimed once in OPA |
| §19 | 2026-09-20 | 0.1.1 | An EFS storage can be mounted: the module makes its mount targets (stage 19) |
| <a id="s54"></a>§54 | 2026-09-20 | 0.1.1 | The run can commit again: stop naming the mirror in a pathspec (stage 54.1) |
| §54 | 2026-09-20 | 0.1.1 | Hygiene bundle IV: forgetting a dead instance, the mirror ignores itself, a message says which asset (stage 54) |
| §19 | 2026-09-20 | 0.1.1 | Stage 19 is AWS only: no GCP resources (operator) |
| <a id="s53"></a>§53 | 2026-09-20 | 0.1.1 | An in-bake assertion can stop the bake (stage 53) |
| <a id="s52"></a>§52 | 2026-09-19 | 0.1.1 | An availability zone is declared, and an incompatible set is refused (stage 52) |
| §19 | 2026-09-19 | 0.1.1 | Stage 19: the image derives from basic-rh-10, the instance stands |
| §19 | 2026-09-19 | 0.1.1 | Stage 19: the operator names the group, the size and the storages |
| <a id="s50"></a>§50 | 2026-09-18 | 0.1.1 | A meta-state record says what it read: the ciphertext, not the plaintext (stage 50) |
| <a id="s51"></a>§51 | 2026-09-18 | 0.1.1 | A derived value inherits its inputs' encryption: names in clear, the address domain hidden (stage 51) |
| <a id="s49"></a>§49 | 2026-09-18 | 0.1.1 | Ciphertext all the way to execution: any value may be encrypted, the emission carries the marker, the run materialises it (stage 49) |
| <a id="s47"></a>§47 | 2026-09-17 | 0.1.1 | The gcs state backend type, declared in the fixture and bound to nothing; every live root stays on S3 (stage 47.4) |
| <a id="s48"></a>§48 | 2026-09-17 | 0.1.1 | Fixture: packer's requirement is the floor alone, CI bakes with the latest (stage 48.1) |
| §48 | 2026-09-17 | 0.1.1 | Hygiene bundle III: the version checkers run, unresolved foreign keys are refused, the three per-load warnings are gone, packer's manifest is run-local (stage 48) |
| §47 | 2026-09-17 | 0.1.1 | The local state backend type; the fixture proves two types and reads across them (stage 47.3-7) |
| §47 | 2026-09-17 | 0.1.1 | State backend contract type-agnostic: a kind per type renders location, backend file and data source; S3 is one kind, the emission unchanged (stage 47.1-2) |
| <a id="s46"></a>§46 | 2026-09-17 | 0.1.1 | Several state backends, used and proven collision-proof; a deployed root's state moves only through --migrate-state (stage 46) |
| <a id="r0-1-1-dev1"></a>release 0.1.1.dev1 | 2026-09-17 | 0.1.1.dev1 | release 0.1.1.dev1 |
| <a id="s41"></a>§41 | 2026-09-17 | 0.1.1 | publish: --index alone, the index's url is the check url; uv refuses an explicit one beside it (stage 41) |
| §41 | 2026-09-17 | 0.1.1 | release and publish read the index's own token name, TEST_PYPI_TOKEN or PYPI_TOKEN, when UV_PUBLISH_TOKEN is unset (stage 41) |
| §41 | 2026-09-17 | 0.1.1 | Releases publish to an index: bump-my-version owns the version, just release probes, publishes, then tags (stage 41) |
| <a id="s45"></a>§45 | 2026-09-17 | 0.1.1 | perform job: the GCE guard loads the configuration, so it carries its environment (stage 45) |
| §45 | 2026-09-17 | 0.1.1 | perform job: the plugin's current download path, and closing steps that need the first record (stage 45) |
| §45 | 2026-09-17 | 0.1.1 | CI performs on main: scoped runs prune within scope, the perform job (stage 45) |
| <a id="s43"></a>§43 | 2026-09-17 | 0.1.1 | Hygiene bundle II: the small things noted since stage 39 (stage 43) |
| <a id="s37"></a>§37 | 2026-09-16 | 0.1.1 | Stage 37: the apply job, inert until its identities exist |
