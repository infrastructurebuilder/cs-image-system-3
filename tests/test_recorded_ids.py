# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Every user and group has one id, across every identity (spec 010).

The core resolves every identity plugin's claims together with the ids
the tree has already recorded: a declared id that collides is refused at
validation, naming the id, both names and both identities; the POSIX
identity is the final fallback and takes an external identity's id for
the same configured name; between external identities nothing defers;
a recorded id never changes, and an id once held is never another
name's. An external identity is stood in for here by claims marked
``external`` (the Okta plugin's own claims are its repository's, spec
010's D3).
"""
from __future__ import annotations

from cs_image_system.contract.identity_vocabulary import Claim
from cs_image_system.engine.posix_ids import Pool, ids_document, resolve_posix_ids

POSIX = "posix-local"
OKTA = "an-external-identity"
OTHER = "another-external-identity"


def _posix(kind: str, name: str, i=None, **kw) -> Claim:
    return Claim("the configuration", kind, name, i, rank=20, identity=POSIX, **kw)  # type: ignore[arg-type]


def _external(kind: str, name: str, i, identity: str = OKTA) -> Claim:
    return Claim("its provider", kind, name, i, rank=3, identity=identity, external=True)  # type: ignore[arg-type]


def _recorded(groups: dict | None = None, users: dict | None = None, retired: dict | None = None) -> dict:
    def entries(d: dict | None) -> dict:
        return {n: {"id": i, "identity": who, "external": who != POSIX, "how": "declared"}
                for n, (i, who) in (d or {}).items()}
    return {"ids": {"group": entries(groups), "user": entries(users)},
            "retired": {"group": dict((retired or {}).get("group", {})), "user": dict((retired or {}).get("user", {}))}}


def _problems(claims, recorded=None) -> list[str]:
    return resolve_posix_ids(claims, recorded=recorded).problems


def test_a_posix_group_on_an_external_groups_id_is_refused_naming_both():
    problems = _problems([_external("group", "coops", 180007), _posix("group", "pxgroup", 180007)])
    assert len(problems) == 1
    p = problems[0]
    assert "180007" in p and "coops" in p and "pxgroup" in p and OKTA in p and POSIX in p
    assert "cannot move" in p                                            # the external id is the one that stays


def test_a_posix_user_on_another_identitys_user_id_is_refused():
    problems = _problems([_external("user", "avery.alpha", 150006), _posix("user", "taylor_tango", 150006)])
    assert len(problems) == 1 and "avery.alpha" in problems[0] and "taylor_tango" in problems[0]


def test_a_recorded_name_declared_with_another_id_is_refused():
    problems = _problems([_posix("group", "pxgroup", 3102)], recorded=_recorded(groups={"pxgroup": (3101, POSIX)}))
    assert len(problems) == 1 and "3101" in problems[0] and "3102" in problems[0]
    assert "does not change" in problems[0]


def test_a_users_private_group_id_taken_by_another_group_names_the_user():
    claims = [_posix("user", "taylor_tango", 3201),
              _posix("group", "taylor_tango", 3201, derived=True),
              _posix("group", "pxgroup", 3201)]
    problems = _problems(claims)
    assert len(problems) == 1 and "3201" in problems[0] and "pxgroup" in problems[0]
    assert "taylor_tango's private group" in problems[0]


def test_a_tree_with_no_collision_passes_with_one_id_each():
    r = resolve_posix_ids([_external("group", "coops", 180007), _posix("group", "pxgroup", 3101),
                           _posix("user", "taylor_tango", 3201)])
    assert r.problems == []
    assert r.ids == {("group", "coops"): 180007, ("group", "pxgroup"): 3101, ("user", "taylor_tango"): 3201}


def test_a_posix_name_an_external_identity_holds_takes_its_id():
    r = resolve_posix_ids([_external("user", "abc", 15001), _posix("user", "abc")])
    assert r.problems == [] and r.ids[("user", "abc")] == 15001
    assert r.defers == {("user", "abc"): OKTA}                           # recorded once, under the external identity


def test_a_posix_name_declared_with_another_id_than_its_external_namesake_is_told_which():
    problems = _problems([_external("user", "abc", 15001), _posix("user", "abc", 15002)])
    assert len(problems) == 1 and "15001" in problems[0] and "15002" in problems[0]
    assert "must be 15001" in problems[0] and "defers" in problems[0]


def test_a_posix_name_recorded_first_that_an_external_identity_later_holds_is_refused():
    problems = _problems([_external("user", "abc", 15001), _posix("user", "abc")],
                         recorded=_recorded(users={"abc": (20003, POSIX)}))
    assert len(problems) == 1 and "20003" in problems[0] and "15001" in problems[0]
    assert "names must" in problems[0]                               # one of them must change


def test_two_external_identities_that_collide_are_a_configuration_error():
    by_name = _problems([_external("group", "coops", 180007), _external("group", "coops", 180008, OTHER)])
    by_id = _problems([_external("group", "coops", 180007), _external("group", "tcmet", 180007, OTHER)])
    for problems in (by_name, by_id):
        assert len(problems) == 1 and OKTA in problems[0] and OTHER in problems[0]
        assert "configuration error" in problems[0]


def test_an_id_once_held_is_never_another_names():
    retired = _recorded(retired={"group": {"oldgroup": 3105}})
    problems = _problems([_posix("group", "pxgroup", 3105)], recorded=retired)
    assert len(problems) == 1 and "3105" in problems[0] and "oldgroup" in problems[0]
    assert _problems([_posix("group", "oldgroup", 3105)], recorded=retired) == []     # its own name takes it back


def test_validation_reads_the_recorded_ids_and_refuses_a_moved_one(tmp_path, monkeypatch):
    """Through `validate`: the fixture declares pxgroup 3101 on the POSIX
    identity; a tree that recorded it as 3102 is refused, from the records
    alone (no network)."""
    import yaml
    from harness import FixtureRun, copy_config

    from cs_image_system.engine.commands.validate import check_posix_ids
    root = copy_config(tmp_path)
    (root / "meta-state" / "ids.yaml").write_text(yaml.safe_dump(
        {"ids": {"group": {"pxgroup": {"id": 3102, "identity": POSIX, "external": False, "how": "declared"}},
                 "user": {}}}))
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    try:
        problems = [str(e) for e in check_posix_ids(run.ctx)]
    finally:
        run.restore_cwd()
    assert any("pxgroup" in p and "3102" in p and "3101" in p and "does not change" in p for p in problems), problems


# ------------------------------------------------- story 2: pools that never drift

POOL = Pool(POSIX, 3000, 3010)


def _recorded_doc(r, recorded=None, pools=(POOL,)) -> dict:
    return ids_document(r, recorded, pools, "run-1")


def test_an_undeclared_name_takes_the_lowest_id_no_name_holds_claims_or_once_held():
    recorded = _recorded(users={"bea": (3001, POSIX)}, retired={"group": {"gone": 3002}})
    r = resolve_posix_ids([_posix("group", "ada", 3000), _posix("user", "bea"), _posix("group", "cal")],
                          recorded=recorded, pools=[POOL])
    assert r.problems == [] and r.ids[("group", "cal")] == 3003 and r.hows[("group", "cal")] == "pooled"


def test_a_recorded_pooled_id_never_drifts_as_names_come_go_and_reorder():
    first = resolve_posix_ids([_posix("group", "mid"), _posix("group", "zed")], pools=[POOL])
    doc = _recorded_doc(first)
    assert doc["ids"]["group"]["mid"]["id"] == 3000 and doc["ids"]["group"]["mid"]["how"] == "pooled"
    later = resolve_posix_ids([_posix("group", "abe"), _posix("group", "mid")], recorded=doc, pools=[POOL])
    assert later.problems == [] and later.ids[("group", "mid")] == 3000
    assert later.ids[("group", "abe")] == 3002                     # zed's 3001 is retired, never given again
    assert _recorded_doc(later, doc)["retired"]["group"] == {"zed": 3001}


def test_a_later_declaration_of_the_recorded_id_passes_and_another_fails():
    doc = _recorded_doc(resolve_posix_ids([_posix("group", "mid")], pools=[POOL]))
    assert _problems([_posix("group", "mid", 3000)], recorded=doc) == []
    problems = _problems([_posix("group", "mid", 3005)], recorded=doc)
    assert len(problems) == 1 and "3000" in problems[0] and "3005" in problems[0] and "does not change" in problems[0]


def test_an_exhausted_pool_fails_naming_its_bounds():
    small = Pool(POSIX, 3000, 3001)
    r = resolve_posix_ids([_posix("group", "a", 3000), _posix("group", "b", 3001), _posix("group", "c")], pools=[small])
    assert len(r.problems) == 1 and "3000-3001" in r.problems[0] and "no free id" in r.problems[0]


def test_a_name_whose_identity_has_no_pool_is_refused():
    problems = _problems([_posix("group", "c")])
    assert len(problems) == 1 and "no pool" in problems[0] and "gid" in problems[0]


def test_a_plain_dry_run_records_nothing_and_a_commit_or_an_applying_run_records():
    from cs_image_system.engine.commands.run_lifecycles import records_ids
    assert records_ids(dry_run=True, commit=False) is False
    assert records_ids(dry_run=True, commit=True) is True and records_ids(dry_run=False, commit=False) is True


def test_the_record_step_writes_the_ids_and_a_plain_dry_run_does_not(tmp_path, monkeypatch):
    from harness import FixtureRun, copy_config

    from cs_image_system.engine.commands.run_lifecycles import settle_ids
    root = copy_config(tmp_path)
    ids_file = root / "meta-state" / "ids.yaml"
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    try:
        settle_ids(run.ctx, record=False)
        assert not ids_file.exists()
        settle_ids(run.ctx, record=True)
        recorded = run.ctx.meta_state.recorded_ids()
    finally:
        run.restore_cwd()
    assert recorded["ids"]["group"]["pxgroup"]["id"] == 3101
    assert recorded["ids"]["user"]["taylor_tango"]["id"] == 3201
    assert "taylor_tango" not in recorded["ids"]["group"]               # a private group is recorded on its user
    assert recorded["pools"]["posix-local"] == {"min": 3000, "max": 59999, "how": "declared"}


def test_an_external_identitys_new_group_is_an_id_to_come_and_draws_nothing():
    from cs_image_system.contract.identity_vocabulary import DEFERRED
    new = Claim("its provider", "group", "fresh", DEFERRED, rank=3, identity=OKTA, external=True)
    r = resolve_posix_ids([new, _posix("group", "fresh")], pools=[POOL])
    assert r.problems == [] and ("group", "fresh") in r.deferred and ("group", "fresh") not in r.ids


def test_two_identities_pools_that_overlap_fail_naming_both():
    okta = Pool(OKTA, 3005, 4000, external=True)
    problems = _problems_pooled([_posix("group", "a", 3001)], pools=[POOL, okta])
    assert len(problems) == 1 and POSIX in problems[0] and OKTA in problems[0] and "3005-3010" in problems[0]


def test_two_posix_builders_may_share_one_pool():
    users = Pool("posix-users", 3000, 3010)
    r = resolve_posix_ids([_posix("group", "g"), Claim("the configuration", "user", "u", None, rank=20,
                                                        identity="posix-users")], pools=[POOL, users])
    assert r.problems == [] and r.ids[("group", "g")] != r.ids[("user", "u")]


def test_a_recorded_id_a_pool_change_leaves_outside_is_kept_and_noted():
    r = resolve_posix_ids([_posix("group", "pxgroup")], recorded=_recorded(groups={"pxgroup": (3101, POSIX)}),
                          pools=[Pool(POSIX, 4000, 5000)])
    assert r.problems == [] and r.ids[("group", "pxgroup")] == 3101
    assert len(r.notes) == 1 and "3101" in r.notes[0] and "kept" in r.notes[0]


def test_a_pool_moved_over_another_identitys_recorded_id_fails_naming_it():
    recorded = _recorded(groups={"coops": (180007, OKTA)})
    problems = _problems_pooled([_external("group", "coops", 180007)], recorded=recorded,
                                pools=[Pool(POSIX, 170000, 190000)])
    assert len(problems) == 1 and "180007" in problems[0] and "coops" in problems[0] and OKTA in problems[0]


def test_a_declared_id_inside_another_identitys_pool_fails():
    problems = _problems_pooled([_posix("group", "a", 4100)], pools=[POOL, Pool(OKTA, 4000, 5000, external=True)])
    assert len(problems) == 1 and "4100" in problems[0] and OKTA in problems[0]


def test_a_user_and_its_private_group_draw_one_id():
    claims = [Claim("the configuration", "user", "pat", None, rank=20, identity=POSIX),
              Claim("the configuration (user-private group)", "group", "pat", None, rank=20, derived=True,
                    identity=POSIX),
              _posix("group", "other")]
    r = resolve_posix_ids(claims, pools=[POOL])
    assert r.problems == [] and r.ids[("user", "pat")] == r.ids[("group", "pat")] == 3000
    assert r.ids[("group", "other")] == 3001


def test_a_pool_below_the_floor_or_upside_down_is_refused_at_load():
    import pytest

    from cs_image_system.posix_identity_plugin.posix_models import checked_pool
    assert checked_pool((3000, 59999), "b") == (3000, 59999)
    for bad in ((100, 5000), (5000, 4000)):
        with pytest.raises(ValueError, match="id_pool"):
            checked_pool(bad, "group builder b")


def _problems_pooled(claims, recorded=None, pools=()) -> list[str]:
    return resolve_posix_ids(claims, recorded=recorded, pools=pools).problems



# --------------------------------------- story 3: an external identity beside POSIX

def _with_external_identities(tmp_path, monkeypatch, holds: dict[str, dict[str, int]],
                              recorded: dict | None = None):
    """A fixture copy with one test-local external identity per entry of
    ``holds`` (builder name -> group name -> the id its provider assigned),
    the first answering the pool 170000-189999 and each next one the 20,000
    ids above; ``recorded`` is written as
    ``meta-state/ids.yaml`` first. Returns the loaded run."""
    import yaml
    from external_identity import EXTERNAL_POOL, stub_external_identity
    from harness import FixtureRun, copy_config
    stub_external_identity(monkeypatch)
    root = copy_config(tmp_path)
    path = root / "cfg" / "group-builders.yml"
    data = yaml.safe_load(path.read_text())
    data["group_builders"] += [{"name": name, "type": "test-external", "holds": dict(groups),
                                "id_pool": [EXTERNAL_POOL[0] + 20000 * n, EXTERNAL_POOL[1] + 20000 * n]}
                               for n, (name, groups) in enumerate(holds.items())]   # apart, as pools must be
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    if recorded is not None:
        (root / "meta-state" / "ids.yaml").write_text(yaml.safe_dump(recorded, sort_keys=False))
    return FixtureRun(tmp_path, monkeypatch, config_root=root), root


def _validate_and_record(run, record: bool = True) -> list[str]:
    from cs_image_system.engine.commands.run_lifecycles import settle_ids
    from cs_image_system.engine.commands.validate import check_posix_ids
    problems = [str(e) for e in check_posix_ids(run.ctx)]
    if not problems and record:
        settle_ids(run.ctx, record=True)
    return problems


def test_an_external_groups_id_read_first_is_recorded_as_read_with_its_pool(tmp_path, monkeypatch):
    run, _root = _with_external_identities(tmp_path, monkeypatch, {"ext-a": {"coops": 180007}})
    try:
        assert _validate_and_record(run) == []
        doc = run.ctx.meta_state.recorded_ids()
    finally:
        run.restore_cwd()
    assert doc["ids"]["group"]["coops"] == {"id": 180007, "identity": "ext-a", "external": True, "how": "read",
                                            "recorded_run": doc["ids"]["group"]["coops"]["recorded_run"]}
    assert doc["pools"]["ext-a"] == {"min": 170000, "max": 189999, "how": "read"}
    # no declared and no pooled id may take it afterwards
    assert len(_problems([_posix("group", "pxother", 180007)], recorded=doc)) == 1
    drawn = resolve_posix_ids([_posix("group", "fresh")], recorded=doc, pools=[Pool(POSIX, 180007, 180008)])
    assert drawn.ids[("group", "fresh")] == 180008


def test_a_later_read_of_another_id_is_refused_and_the_record_kept(tmp_path, monkeypatch):
    recorded = _recorded(groups={"coops": (180007, "ext-a")})
    run, root = _with_external_identities(tmp_path, monkeypatch, {"ext-a": {"coops": 180008}}, recorded=recorded)
    before = (root / "meta-state" / "ids.yaml").read_text()
    try:
        problems = _validate_and_record(run)
    finally:
        run.restore_cwd()
    assert len(problems) == 1 and "180007" in problems[0] and "180008" in problems[0] and "ext-a" in problems[0]
    assert (root / "meta-state" / "ids.yaml").read_text() == before


def test_an_external_id_read_onto_a_posix_names_recorded_id_is_refused_naming_both(tmp_path, monkeypatch):
    recorded = _recorded(groups={"pxgroup": (3101, "posix-local")})
    run, _root = _with_external_identities(tmp_path, monkeypatch, {"ext-a": {"coops": 3101}}, recorded=recorded)
    try:
        problems = _validate_and_record(run, record=False)
    finally:
        run.restore_cwd()
    hit = [p for p in problems if "3101" in p]
    assert len(hit) == 1 and "coops" in hit[0] and "pxgroup" in hit[0] and "cannot move" in hit[0]


def test_a_second_external_identity_joins_the_same_check_with_no_core_change(tmp_path, monkeypatch):
    run, _root = _with_external_identities(tmp_path, monkeypatch,
                                           {"ext-a": {"coops": 180007}, "ext-b": {"tcmet": 180007}})
    try:
        problems = _validate_and_record(run, record=False)
    finally:
        run.restore_cwd()
    hit = [p for p in problems if "180007" in p]
    assert len(hit) == 1 and "coops" in hit[0] and "tcmet" in hit[0] and "configuration error" in hit[0]
