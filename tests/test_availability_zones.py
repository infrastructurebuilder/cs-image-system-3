# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 52: an availability zone is declared, never inferred, and a set that
is not compatible is refused at validate.

Compatible, not identical: an unset zone constrains nothing, and a REGIONAL
storage (EFS, S3, GCS) constrains nothing either. What is refused is more than
one distinct zone across an instance, the zonal storages it mounts, and its
runtime's subnet -- because a zone is a replace-forcing attribute, so the
alternative to this refusal is a plan that destroys and recreates a volume.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from cs_image_system.base.commands.validate import check_availability_zones

if TYPE_CHECKING:
    from cs_image_system.base.global_context import GlobalTypeContext


def _ctx(*, storages=None, instances=None, runtimes=None, builders=None):
    # storages and instances are LISTS on the real context; the builders are
    # dicts keyed by name
    # the check reads four collections off the context; a stand-in carrying
    # those is the whole fixture it needs
    return cast("GlobalTypeContext", SimpleNamespace(
        storages=list((storages or {}).values()),
        instances=list((instances or {}).values()),
        runtime_builders=runtimes or {}, storage_builders=builders or {}))


def _storage(name, *, type_="aws-ebs", runtime="aws", zone=None):
    return SimpleNamespace(availability_zone=zone, runtime=runtime,
                           get_type=lambda: type_, get_name=lambda: name)


def _instance(name, *, runtime="aws", zone=None, storages=()):
    return SimpleNamespace(availability_zone=zone, runtime=runtime,
                           storages=[SimpleNamespace(name=s) for s in storages],
                           get_name=lambda: name)


def _runtime(*, subnet_zone=None, default_zone=None, subnet_name="az1-private"):
    subnet = SimpleNamespace(availability_zone=subnet_zone, get_name=lambda: subnet_name)
    net = SimpleNamespace(default_availability_zone=default_zone, default_subnet=subnet)
    return SimpleNamespace(model=SimpleNamespace(networking=net))


ZONAL = SimpleNamespace(is_zonal=lambda: True)
REGIONAL = SimpleNamespace(is_zonal=lambda: False)


def test_one_zone_everywhere_is_fine():
    ctx = _ctx(storages={"vol": _storage("vol", zone="us-east-2a")},
               instances={"i": _instance("i", storages=["vol"])},
               runtimes={"aws": _runtime(subnet_zone="us-east-2a")},
               builders={"aws-ebs": ZONAL})
    assert check_availability_zones(ctx) == []


def test_a_zonal_storage_in_another_zone_than_its_runtime_is_refused():
    ctx = _ctx(storages={"vol": _storage("vol", zone="us-east-2a")},
               runtimes={"aws": _runtime(subnet_zone="us-east-2b")},
               builders={"aws-ebs": ZONAL})
    errs = check_availability_zones(ctx)
    assert len(errs) == 1
    assert "us-east-2a" in str(errs[0]) and "us-east-2b" in str(errs[0]) and "REPLACES" in str(errs[0])


def test_an_instance_cannot_be_in_two_zones():
    ctx = _ctx(storages={"vol": _storage("vol", zone="us-east-2a")},
               instances={"i": _instance("i", zone="us-east-2b", storages=["vol"])},
               runtimes={"aws": _runtime()},
               builders={"aws-ebs": ZONAL})
    errs = check_availability_zones(ctx)
    assert len(errs) == 1
    message = str(errs[0])
    assert "instance 'i'" in message and "storage 'vol'" in message
    assert "us-east-2a" in message and "us-east-2b" in message


def test_an_unset_zone_constrains_nothing():
    """The point of 'compatible' rather than 'identical'."""
    ctx = _ctx(storages={"vol": _storage("vol", zone=None)},
               instances={"i": _instance("i", zone="us-east-2b", storages=["vol"])},
               runtimes={"aws": _runtime()},
               builders={"aws-ebs": ZONAL})
    assert check_availability_zones(ctx) == []


def test_a_regional_storage_constrains_nothing():
    """EFS is reachable from every zone, so its declared zone -- if someone
    sets one -- is not a constraint on the instance."""
    ctx = _ctx(storages={"share": _storage("share", type_="aws-efs", zone="us-east-2a")},
               instances={"i": _instance("i", zone="us-east-2b", storages=["share"])},
               runtimes={"aws": _runtime()},
               builders={"aws-efs": REGIONAL})
    assert check_availability_zones(ctx) == []


def test_the_runtimes_declared_zone_wins_over_its_subnets():
    ctx = _ctx(instances={"i": _instance("i", zone="us-east-2b")},
               runtimes={"aws": _runtime(subnet_zone="us-east-2b", default_zone="us-east-2a")},
               builders={})
    errs = check_availability_zones(ctx)
    assert len(errs) == 1 and "us-east-2a" in str(errs[0])


def test_the_error_names_every_claimant():
    ctx = _ctx(storages={"a": _storage("a", zone="us-east-2a"), "b": _storage("b", zone="us-east-2c")},
               instances={"i": _instance("i", storages=["a", "b"])},
               runtimes={"aws": _runtime(subnet_zone="us-east-2b")},
               builders={"aws-ebs": ZONAL})
    errs = [str(e) for e in check_availability_zones(ctx)]
    # each zonal storage is refused against its runtime, AND the instance is
    # refused for being asked into three zones at once
    message = next(e for e in errs if "instance 'i'" in e)
    for needle in ("storage 'a'", "storage 'b'", "subnet", "us-east-2a", "us-east-2b", "us-east-2c"):
        assert needle in message, needle


def test_a_declared_zone_reaches_the_module_call():
    """Declaring a zone must PIN it, or validate would be checking a value the
    emission ignores -- the module derives one from the subnet otherwise."""
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuEbsStorageBuilder
    import inspect
    src = inspect.getsource(TofuEbsStorageBuilder.module_args)
    assert 'getattr(storage, "availability_zone", None)' in src
    assert src.index('getattr(storage, "availability_zone", None)') < src.index("default_availability_zone")
