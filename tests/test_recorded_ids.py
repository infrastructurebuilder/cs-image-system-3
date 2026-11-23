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
from cs_image_system.engine.posix_ids import resolve_posix_ids

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
