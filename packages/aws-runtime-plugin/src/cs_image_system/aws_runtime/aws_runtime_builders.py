# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Mapping
from typing import Any


from cs_image_system.base.basic.abstract_version_checker import AbstractVersionChecker
from cs_image_system.base.basic.asset import AssetSet
from cs_image_system.base.basic.builder_base_cloud import CloudBuilderBase
from cs_image_system.base.constants import VCT
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage
from cs_image_system.base.protocols.plugin_metadata import PluginArtifactProtocol

from .aws_provider_specific_image import AwsProviderSpecificImage
from .aws_runtime_models import AWS_CLI, AwsCloudBuilderModel
from .aws_utils import remap_for_image_query, query_image
from cs_image_system.aws_runtime import aws_utils

log = logging.getLogger(__name__)


AWS_RUNTIME: str = "aws"  



class AwsCloudBuilder(CloudBuilderBase[AwsCloudBuilderModel], PluginArtifactProtocol):
    """AWS cloud provider implementation."""

    @classmethod
    def csis_name(cls) -> str:
        return AWS_RUNTIME

    @property
    def model(self) -> AwsCloudBuilderModel:
        return self._model # type: ignore

    def provider_specific_image_class(self) -> type[ProviderSpecificImage]:
        return AwsProviderSpecificImage

    def query_provider_image(self, os_builder: OSBuilderBaseImageBuilderSubconfig) -> tuple[str, str, Mapping[str,Any]] | None:
        retval: str | None = None
        q,missed = remap_for_image_query(os_builder) if os_builder else ({}, {})
        kv = query_image(
                query=q,
                post_query_filter=missed,
                session_config=self.model.self_to_aws_client_config(),
            )
        if kv:
            retval = kv.get("ImageId", None)
        else:
            kv = {}
        
        regstr = "self"
        if retval:
            region = self.model.get_region()
            if not region:
                raise ValueError(f"Region must be specified in builder config to resolve image identifier, but got {region}")
            reg = aws_utils.get_ami_owner(kv)
            if not reg:
                raise ValueError(f"Could not get owner for image {retval} in region {region}")
            _r = reg.get("ImageOwnerAlias", None)
            if not _r:
                _r = reg.get("OwnerId", None)
            if not _r:
                raise ValueError(f"Could not get owner alias or owner id for image {retval} in region {region}, got {reg}")
            regstr = str(_r)
        return (retval,regstr, kv) if retval else None

    # def resolve_image_for_os_builder(
    #     self, os_builder: OsBuilderProtocol
    # ) -> Image | None:
    #     ret: Image | None = None
    #     rc = os_builder.get_configs_for_runtimes().get(self.name,None)
    #     assert rc is not None, f"No runtime configuration found for runtime type {self.name} in OS builder {os_builder.get_name()}"
    #     # q, missed = aws_utils.remap_for_image_query(rc)
    #     # kv = aws_utils.query_image(
    #     #         query=q,
    #     #         post_query_filter=missed,
    #     #         session_config=self.model.self_to_aws_client_config(),
    #     #     )

    #     kv = os_builder.get_runtime_config_query_results(self)
    #     if kv:
    #         ret = image_from_query_result(   # stage 24: that function is gone; see aws_utilskv, os_builder, self)
    #     return ret

    def query_images(self, series: list[str]) -> list[dict[str, Any]]:
        """Every AMI we own that carries a ``csis_series`` tag (read-only)."""
        from cs_image_system.base.lineage import TAG_PREFIX
        ec2 = aws_utils.ec2_client(self.model.self_to_aws_client_config())
        out: list[dict[str, Any]] = []
        paginator = ec2.get_paginator("describe_images")
        for page in paginator.paginate(Owners=["self"],
                                       Filters=[{"Name": "tag-key", "Values": [f"{TAG_PREFIX}series"]}]):
            for img in page.get("Images", []):
                tags = {t["Key"]: t["Value"] for t in img.get("Tags", []) if "Key" in t}
                out.append({"image_id": img.get("ImageId"), "name": img.get("Name"),
                            "state": img.get("State"), "created": img.get("CreationDate"),
                            "tags": tags})
        return out

    # ----------------------------------------------- AWS parity (stage 11.1)
    def _running_instance(self, instance_name: str) -> dict[str, Any] | None:
        ec2 = aws_utils.ec2_client(self.model.self_to_aws_client_config())
        res = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [instance_name]},
                                              {"Name": "instance-state-name", "Values": ["pending", "running"]}])
        found = [i for r in res.get("Reservations", []) for i in r.get("Instances", [])]
        return found[0] if found else None

    def can_query_instance_boot_image(self) -> bool:
        return True

    def query_instance_boot_image(self, instance_name: str) -> str | None:
        """The AMI the named instance runs (its ``ImageId``); None when no
        such instance is running -- read-only, never fatal."""
        try:
            inst = self._running_instance(instance_name)
            return str(inst.get("ImageId")) if inst and inst.get("ImageId") else None
        except Exception as e:  # noqa: BLE001 - read-only probe
            log.debug(f"AWS runtime {self.get_name()}: boot image of {instance_name!r} unavailable: {e}")
            return None

    def dispose_image(self, build_id: str) -> bool:
        """Deregister the AMI and delete the EBS snapshots it was made of --
        the finding-46 shape done by hand for two AMIs on 2026-09-05.
        Not found = already gone (the record is still dropped)."""
        ec2 = aws_utils.ec2_client(self.model.self_to_aws_client_config())
        try:
            images = ec2.describe_images(ImageIds=[build_id]).get("Images", [])
        except Exception as e:  # noqa: BLE001
            if "InvalidAMIID" in str(e) or "NotFound" in str(e):
                log.warning(f"AMI {build_id} not found; nothing to deregister")
                return False
            raise
        if not images:
            log.warning(f"AMI {build_id} not found; nothing to deregister")
            return False
        snapshots = [m["Ebs"]["SnapshotId"] for m in images[0].get("BlockDeviceMappings", [])
                     if m.get("Ebs", {}).get("SnapshotId")]
        ec2.deregister_image(ImageId=build_id)
        for snap in snapshots:
            ec2.delete_snapshot(SnapshotId=snap)
        log.info(f"AMI {build_id} deregistered; snapshots deleted: {snapshots or 'none'}")
        return True

    def verify_instance(self, instance_name: str, expected_build: str | None = None,
                        expect_mounts: int = 0, timeout: int = 600) -> dict[str, Any]:
        """Over SSM: the launch parameters' completion marker
        (/var/lib/csis/launch-applied, written as the user-data script's
        last act), the mounts under /mnt, and the AMI the instance runs."""
        import time  # noqa: PLC0415
        checks: list[dict[str, Any]] = []
        deadline = time.time() + timeout
        script = ("test -f /var/lib/csis/launch-applied && echo LAUNCH_APPLIED; "
                  "findmnt -rn -o TARGET | grep -c '^/mnt/' || true")
        out, rc = "", 1
        while True:
            try:
                rc, out = self.run_session_command(instance_name, script, timeout=120)
            except Exception as e:  # noqa: BLE001 - SSM not up yet
                rc, out = 1, str(e)
            if rc == 0 and "LAUNCH_APPLIED" in out:
                break
            if time.time() >= deadline:
                break
            time.sleep(15)
        applied = rc == 0 and "LAUNCH_APPLIED" in out
        checks.append({"name": "startup scripts", "ok": applied,
                       "detail": "launch parameters applied" if applied else f"no completion marker within {timeout}s"})
        booted = self.query_instance_boot_image(instance_name)
        if expected_build:
            checks.append({"name": "booted image", "ok": booted == expected_build,
                           "detail": f"booted {booted}, expected {expected_build}"})
        else:
            checks.append({"name": "booted image", "ok": booted is not None, "detail": f"booted {booted}"})
        if expect_mounts:
            try:
                mounted = int([ln for ln in out.splitlines() if ln.strip().isdigit()][-1])
            except (IndexError, ValueError):
                mounted = 0
            checks.append({"name": "data disks mounted", "ok": mounted >= expect_mounts,
                           "detail": f"{mounted} mount(s) under /mnt, {expect_mounts} declared"})
        return {"ok": all(c["ok"] for c in checks), "checks": checks, "evidence": out.splitlines()[-20:]}

    def run_session_command(self, instance_name: str, script: str, timeout: int = 300) -> tuple[int, str]:
        """SSM ``AWS-RunShellScript`` on the instance named by its Name tag
        (the session mechanism instances are reached by, stage 1)."""
        import time  # noqa: PLC0415
        cfg = self.model.self_to_aws_client_config()
        ec2 = aws_utils.ec2_client(cfg)
        res = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [instance_name]},
                                              {"Name": "instance-state-name", "Values": ["running"]}])
        ids = [i["InstanceId"] for r in res.get("Reservations", []) for i in r.get("Instances", [])]
        if not ids:
            raise RuntimeError(f"AWS runtime {self.get_name()}: no running instance named {instance_name!r}")
        ssm = aws_utils.aws_client("ssm", cfg)
        sent = ssm.send_command(InstanceIds=ids[:1], DocumentName="AWS-RunShellScript",
                                Parameters={"commands": script.splitlines()}, TimeoutSeconds=timeout)
        command_id = sent["Command"]["CommandId"]
        deadline = time.time() + timeout
        while True:
            try:
                inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=ids[0])
            except Exception as e:  # noqa: BLE001
                # the invocation record appears a moment AFTER send_command
                # returns (found live, ledger 72: the unmount had already run
                # on the instance when this raised, so no receipt was written)
                code = str(getattr(e, "response", {}).get("Error", {}).get("Code", "")) if hasattr(e, "response") else ""
                if code == "InvocationDoesNotExist" and time.time() < deadline:
                    time.sleep(2)
                    continue
                raise
            status = inv.get("Status")
            if status in ("Success", "Failed", "TimedOut", "Cancelled"):
                out = (inv.get("StandardOutputContent") or "") + (inv.get("StandardErrorContent") or "")
                return (0 if status == "Success" else 1), out
            if time.time() > deadline:
                return 1, f"ssm command {command_id} still {status} after {timeout}s"
            time.sleep(5)

    def retag_image(self, image_id: str, tags: dict[str, str]) -> bool:
        """``create-tags`` on one of our own AMIs (zero-drift-report)."""
        ec2 = aws_utils.ec2_client(self.model.self_to_aws_client_config())
        ec2.create_tags(Resources=[image_id],
                        Tags=[{"Key": k, "Value": str(v)} for k, v in sorted(tags.items())])
        return True

    # ------------------------------------------------- packer source hooks
    def packer_source_type(self) -> str:
        from .aws_packer_source import AMAZON_EBS
        return AMAZON_EBS

    def packer_source_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                             self_subconfig: Any, psi: Any, tags: dict[str, str],
                             final_name: str, pinned: str | None) -> list[str]:
        from .aws_packer_source import amazon_ebs_source
        return amazon_ebs_source(self.model, image, runtime=runtime, source_type=source_type,
                                 subconfig=subconfig, self_subconfig=self_subconfig, psi=psi,
                                 tags=tags, final_name=final_name, pinned=pinned)

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return super().generate_items_during(phase)

    # ------------------------------------------------------------ V2 (N9)
    SSM = "ssm"

    def session_mechanism(self) -> str | None:
        mech = getattr(self.model, "session_mechanism", None)
        if not mech:
            return None
        mech = str(mech).strip().lower()
        if mech != self.SSM:
            raise ValueError(f"AWS runtime {self.get_name()}: unknown session mechanism {mech!r} "
                             f"(supported: {self.SSM})")
        return mech

    def session_agent_commands(self, os_family: str | None = None) -> list[str]:
        if self.session_mechanism() != self.SSM:
            return []
        fam = (os_family or "").lower()
        region = self.model.get_region()
        if fam in ("debian", "ubuntu"):
            # Guarded: the SSM-communicator bootstrap has usually installed the
            # agent already (and owns /tmp/ssm.deb as root -- found live:
            # curl(23) on re-download); unique filename, root-owned download.
            install = ["command -v amazon-ssm-agent >/dev/null 2>&1 || snap list amazon-ssm-agent >/dev/null 2>&1 || "
                       f"(sudo curl -fsSL https://s3.{region}.amazonaws.com/amazon-ssm-{region}/latest/debian_amd64/amazon-ssm-agent.deb -o /tmp/ssm-agent-bake.deb && sudo dpkg -i /tmp/ssm-agent-bake.deb)"]
        else:
            install = [f"sudo yum install -y https://s3.{region}.amazonaws.com/amazon-ssm-{region}/latest/linux_amd64/amazon-ssm-agent.rpm || sudo yum install -y amazon-ssm-agent"]
        return [f"# session mechanism 'ssm' ({self.get_name()}): SSM agent for debug sessions"] + install + [
            "sudo systemctl enable amazon-ssm-agent"]

    def session_verify_commands(self, os_family: str | None = None) -> list[str]:
        if self.session_mechanism() != self.SSM:
            return []
        return ["# verify: SSM agent baked",
                "command -v amazon-ssm-agent >/dev/null 2>&1 || test -x /usr/bin/amazon-ssm-agent || snap list amazon-ssm-agent >/dev/null 2>&1",
                "systemctl is-enabled amazon-ssm-agent >/dev/null 2>&1 || systemctl is-enabled snap.amazon-ssm-agent.amazon-ssm-agent.service >/dev/null 2>&1"]

    def release_commands(self, build_id: str, tags: dict[str, str]):
        """Mark a released AMI in the cloud: tag it (reviewable, gated by
        config.apply_release)."""
        from cs_image_system.base.models.executable import ExecutableModel
        args = ["ec2", "create-tags", "--region", str(self.model.get_region()), "--resources", build_id, "--tags"]
        args += [f"Key={k},Value={v}" for k, v in sorted(tags.items())]
        creds = self.model.get_credentials()        # stage 17
        if creds.get("profile_name"):
            args += ["--profile", str(creds["profile_name"])]
        e = ExecutableModel(name="aws", type_="executable", binary="aws")
        e.args = args
        return [e]

    def session_instance_profile(self) -> str | None:
        if self.session_mechanism() != self.SSM:
            return None
        return getattr(self.model, "session_instance_profile", None) or None


class AwsCLIVersionChecker(AbstractVersionChecker):
    """Version checker for AWS."""

    @classmethod
    def csis_name(cls) -> str:
        return AWS_CLI


    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.VERSION_CHECKER
    
    def get_regex(self) -> str:
        return r"aws-cli\/([\d\.]+)\s"
