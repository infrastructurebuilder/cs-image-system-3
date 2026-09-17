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

from .gcp_provider_specific_image import GcpProviderSpecificImage
from .gcp_runtime_models import GCPCloudBuilderModel
from cs_image_system.gcloud_runtime import gcp_utils
from .gcp_utils import remap_for_image_query, query_image

GCP_RUNTIME: str = "gcloud"

log = logging.getLogger(__name__)


class GCPCloudBuilder(CloudBuilderBase[GCPCloudBuilderModel], PluginArtifactProtocol):
    """GCP cloud provider implementation."""

    @classmethod
    def csis_name(cls) -> str:
        return GCP_RUNTIME

    @property
    def model(self) -> GCPCloudBuilderModel:
        return self._model # type: ignore

    def provider_specific_image_class(self) -> type[ProviderSpecificImage]:
        return GcpProviderSpecificImage

    def query_provider_image(self, os_builder: OSBuilderBaseImageBuilderSubconfig) -> tuple[str, str, Mapping[str,Any]] | None:
        retval: str | None = None
        q, missed = remap_for_image_query(os_builder) if os_builder else ({}, {})
        kv = query_image(
                query=q,
                post_query_filter=missed,
                session_config=self.model.self_to_gcp_client_config(),
            )
        if kv:
            # The GCP image identifier is its name (unique within a project).
            retval = kv.get("name", None)
        else:
            kv = {}

        ownerstr = "self"
        if retval:
            owner = gcp_utils.get_image_owner(kv)
            if not owner:
                raise ValueError(f"Could not get owning project for image {retval}, got {kv}")
            _p = owner.get("project", None)
            if not _p:
                raise ValueError(f"Could not get owning project for image {retval}, got {owner}")
            ownerstr = str(_p)
        return (retval, ownerstr, kv) if retval else None

    # stage 24: `resolve_image_for_os_builder` was removed here. It was defined
    # only on this builder, had no callers and no base-class declaration, and
    # returned image_from_query_result(...) -- which could never return an
    # Image. The AWS twin was already commented out. Ledger 78.

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return super().generate_items_during(phase)

    # --------------------------------------------- session mechanism (IAP)
    IAP = "iap"

    def session_mechanism(self) -> str | None:
        mech = getattr(self.model, "session_mechanism", None)
        if not mech:
            return None
        mech = str(mech).strip().lower()
        if mech != self.IAP:
            raise ValueError(f"GCP runtime {self.get_name()}: unknown session mechanism {mech!r} "
                             f"(supported: {self.IAP})")
        return mech

    def session_agent_commands(self, os_family: str | None = None) -> list[str]:
        """IAP TCP forwarding needs only sshd and the Google guest agent (key
        provisioning via metadata); the IAP firewall rule (35.235.240.0/20 ->
        22) and roles/iap.tunnelResourceAccessor are operator prerequisites."""
        if self.session_mechanism() != self.IAP:
            return []
        fam = (os_family or "").lower()
        install = ("sudo apt-get -o DPkg::Lock::Timeout=600 install -y google-guest-agent" if fam in ("debian", "ubuntu")
                   else "sudo yum install -y google-guest-agent")
        return ["# debug session mechanism: IAP TCP forwarding (operator: IAP firewall rule + tunnelResourceAccessor)",
                f"command -v google_guest_agent >/dev/null 2>&1 || {install}",
                "sudo systemctl enable google-guest-agent sshd 2>/dev/null || sudo systemctl enable google-guest-agent ssh"]

    def session_verify_commands(self, os_family: str | None = None) -> list[str]:
        if self.session_mechanism() != self.IAP:
            return []
        return ["# verify: guest agent baked for IAP sessions",
                "command -v google_guest_agent >/dev/null 2>&1 || test -x /usr/bin/google_guest_agent",
                "systemctl is-enabled google-guest-agent >/dev/null 2>&1"]

    def bake_ssh_username(self) -> str | None:
        # Mirror googlecompute_source's resolution (finding 48): the model's
        # ssh_username when set, else the "packer" fallback googlecompute has
        # no vendor default, so the source always emits one and provisioners
        # must name the same user.
        from cs_image_system.base.constants import OOPS_DEFAULTS
        mu = getattr(self.model, "ssh_username", None)
        return mu if mu and mu not in OOPS_DEFAULTS else "packer"

    def bake_finalize_commands(self, os_family: str | None = None) -> list[str]:
        # finding 47 (found live at the gce-test launch): a baked image
        # carries the bake's ssh user, and at first boot the guest agent
        # (manager + core-plugin generation) removes users absent from
        # metadata -- if that user's google-sudoers membership is missing
        # (the agents race each other over it during bakes), gpasswd exits 3
        # and the agent ABORTS its entire metadata-ssh-key setup, so no
        # operator key is ever provisioned and every SSH/IAP session is
        # refused. Guarantee the membership as the bake's last act so the
        # first-boot removal always succeeds cleanly.
        return ["# finding 47: the build user must leave the image a clean google-sudoers member",
                'getent group google-sudoers >/dev/null 2>&1 && sudo gpasswd -a "$(whoami)" google-sudoers >/dev/null || true']

    def query_images(self, series: list[str]) -> list[dict[str, Any]]:
        """Every image in the project labelled with ``csis_series`` (read-only)."""
        from cs_image_system.base.lineage import TAG_PREFIX
        from .gcp_utils import _make_images_client, resolve_project
        cfg = self.model.self_to_gcp_client_config()
        project = resolve_project(cfg)
        if not project:
            raise RuntimeError(f"GCP runtime {self.get_name()}: no project to query")
        client = _make_images_client(cfg)
        out: list[dict[str, Any]] = []
        from google.cloud import compute_v1  # noqa: PLC0415
        request = compute_v1.ListImagesRequest(project=project, filter=f"labels.{TAG_PREFIX}series:*")
        for img in client.list(request=request):
            labels = dict(getattr(img, "labels", {}) or {})
            out.append({"image_id": img.name, "name": img.name, "state": str(getattr(img, "status", "")),
                        "created": str(getattr(img, "creation_timestamp", "")), "tags": labels})
        return out

    def serial_console(self, instance_name: str) -> str:
        """The instance's serial port 1 output (read-only)."""
        from .gcp_packer_source import gce_name
        from .gcp_utils import _make_credentials, resolve_project
        from google.cloud import compute_v1  # noqa: PLC0415
        cfg = self.model.self_to_gcp_client_config()
        project, zone = resolve_project(cfg), getattr(self.model, "zone", None)
        if not project or not zone:
            raise RuntimeError(f"GCP runtime {self.get_name()}: no project/zone to read a serial console")
        creds = _make_credentials(cfg)
        kw = {"credentials": creds} if creds else {}
        out = compute_v1.InstancesClient(**kw).get_serial_port_output(
            project=project, zone=zone, instance=gce_name(instance_name))
        return str(getattr(out, "contents", "") or "")

    def verify_instance(self, instance_name: str, expected_build: str | None = None,
                        expect_mounts: int = 0, timeout: int = 600) -> dict[str, Any]:
        """stage 10.2 -- what `just gce-verify` did by hand: poll the serial
        console until the guest agent reports the startup scripts finished
        (agent >= 20260715: "Finished running startup scripts"; older:
        "startup-script exit status 0"), fail fast on an explicit failure
        line, then compare the booted image with the expected build and
        count the kernel's clean XFS mounts against the declared data
        disks."""
        import re  # noqa: PLC0415
        import time  # noqa: PLC0415
        checks: list[dict[str, Any]] = []
        deadline = time.time() + timeout
        out = ""
        while True:
            out = self.serial_console(instance_name)
            if re.search(r"startup-script exit status [1-9]|startup-script.*(failed|error)", out, re.I):
                checks.append({"name": "startup scripts", "ok": False, "detail": "an explicit failure line"})
                break
            if re.search(r"Finished running startup scripts|startup-script exit status 0", out):
                checks.append({"name": "startup scripts", "ok": True, "detail": "finished"})
                break
            if time.time() >= deadline:
                checks.append({"name": "startup scripts", "ok": False,
                               "detail": f"no completion on the serial console within {timeout}s"})
                break
            time.sleep(15)
        booted = self.query_instance_boot_image(instance_name)
        if expected_build:
            checks.append({"name": "booted image", "ok": booted == expected_build,
                           "detail": f"booted {booted}, expected {expected_build}"})
        else:
            checks.append({"name": "booted image", "ok": booted is not None, "detail": f"booted {booted}"})
        if expect_mounts:
            mounted = len(re.findall(r"XFS \([a-z0-9]+\): Ending clean mount", out))
            checks.append({"name": "data disks mounted", "ok": mounted >= expect_mounts,
                           "detail": f"{mounted} clean XFS mount(s) on the console, {expect_mounts} declared"})
        evidence = [ln for ln in out.splitlines()
                    if re.search(r"startup|XFS|google_metadata_script_runner", ln)][-20:]
        return {"ok": all(c["ok"] for c in checks), "checks": checks, "evidence": evidence}

    def run_session_command(self, instance_name: str, script: str, timeout: int = 300) -> tuple[int, str]:
        """``gcloud compute ssh --tunnel-through-iap --command`` as the
        operator's gcloud account (the IAP grant, stage 2)."""
        import subprocess  # noqa: PLC0415
        from .gcp_packer_source import gce_name
        from .gcp_utils import resolve_project
        cfg = self.model.self_to_gcp_client_config()
        project, zone = resolve_project(cfg), getattr(self.model, "zone", None)
        if not project or not zone:
            raise RuntimeError(f"GCP runtime {self.get_name()}: no project/zone for a session command")
        cmd = ["gcloud", "compute", "ssh", gce_name(instance_name), "--project", str(project), "--zone", str(zone),
               "--tunnel-through-iap", "--quiet", "--command", script]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
        return res.returncode, (res.stdout or "") + (res.stderr or "")

    def inventory(self) -> dict[str, list[str]]:
        """Instances and disks in the runtime's zone, every custom image in
        the project, and the project's buckets (via gcloud, no extra library)."""
        import subprocess  # noqa: PLC0415
        from google.cloud import compute_v1  # noqa: PLC0415
        from .gcp_utils import _make_credentials, resolve_project
        cfg = self.model.self_to_gcp_client_config()
        project, zone = resolve_project(cfg), getattr(self.model, "zone", None)
        if not project or not zone:
            raise RuntimeError(f"GCP runtime {self.get_name()}: no project/zone to inventory")
        creds = _make_credentials(cfg)
        kw = {"credentials": creds} if creds else {}
        instances = sorted(i.name for i in compute_v1.InstancesClient(**kw).list(project=project, zone=zone))
        images = sorted(i.name for i in compute_v1.ImagesClient(**kw).list(project=project))
        disks = sorted(d.name for d in compute_v1.DisksClient(**kw).list(project=project, zone=zone))
        res = subprocess.run(["gcloud", "storage", "buckets", "list", "--project", str(project), "--format=value(name)"],
                             capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"gcloud storage buckets list: {(res.stderr or '').strip()[-300:]}")
        buckets = sorted(ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip())
        return {"instances": instances, "images": images, "disks": disks, "buckets": buckets}

    def dispose_image(self, build_id: str) -> bool:
        """Delete the GCE image named by the build id and wait for the
        operation (stage 8.4). NotFound = already gone."""
        from google.api_core.exceptions import NotFound  # noqa: PLC0415
        from .gcp_utils import _make_images_client, resolve_project
        cfg = self.model.self_to_gcp_client_config()
        project = resolve_project(cfg)
        if not project:
            raise RuntimeError(f"GCP runtime {self.get_name()}: no project to dispose in")
        client = _make_images_client(cfg)
        try:
            client.delete(project=project, image=build_id).result()
        except NotFound:
            log.warning(f"GCE image {build_id} not found in {project}; nothing to delete")
            return False
        log.info(f"GCE image {build_id} deleted from {project}")
        return True

    def retag_image(self, image_id: str, tags: dict[str, str]) -> bool:
        """``setLabels`` on one of our own GCE images (zero-drift-report,
        ledger 66): the labels packer wrote at generation time are merged
        with the lineage truth, through the same ``gce_label`` sanitizer the
        packer source used, so the state query compares like with like."""
        from google.cloud import compute_v1  # noqa: PLC0415
        from .gcp_packer_source import gce_label
        from .gcp_utils import _make_images_client, resolve_project
        cfg = self.model.self_to_gcp_client_config()
        project = resolve_project(cfg)
        if not project:
            raise RuntimeError(f"GCP runtime {self.get_name()}: no project to relabel in")
        client = _make_images_client(cfg)
        current = client.get(project=project, image=image_id)
        labels = dict(getattr(current, "labels", {}) or {})
        labels.update({gce_label(k): gce_label(str(v)) for k, v in tags.items()})
        client.set_labels(
            project=project, resource=image_id,
            global_set_labels_request_resource=compute_v1.GlobalSetLabelsRequest(
                label_fingerprint=str(getattr(current, "label_fingerprint", "") or ""), labels=labels),
        ).result()
        log.info(f"GCE image {image_id} relabelled with {sorted(tags)} in {project}")
        return True

    def can_query_instance_boot_image(self) -> bool:
        return True

    def query_instance_boot_image(self, instance_name: str) -> str | None:
        """The GCE image name the instance's boot disk was created from
        (finding 49): instance -> boot disk -> disk.source_image basename.
        Read-only; None when the instance, disk, zone or project cannot be
        resolved, so the caller makes no claim."""
        from .gcp_packer_source import gce_name
        from .gcp_utils import _make_credentials, resolve_project
        try:
            from google.cloud import compute_v1  # noqa: PLC0415
            cfg = self.model.self_to_gcp_client_config()
            project = resolve_project(cfg)
            zone = getattr(self.model, "zone", None)
            if not project or not zone:
                return None
            creds = _make_credentials(cfg)
            kw = {"credentials": creds} if creds else {}
            inst = compute_v1.InstancesClient(**kw).get(project=project, zone=zone,
                                                        instance=gce_name(instance_name))
            boot = next((d for d in (inst.disks or []) if getattr(d, "boot", False)), None)
            if boot is None or not getattr(boot, "source", None):
                return None
            disk_name = str(boot.source).rsplit("/", 1)[-1]
            disk = compute_v1.DisksClient(**kw).get(project=project, zone=zone, disk=disk_name)
            src = getattr(disk, "source_image", None)
            return str(src).rsplit("/", 1)[-1] if src else None
        except Exception as e:  # noqa: BLE001 - read-only probe: unavailable, never fatal
            log.debug(f"GCE runtime {self.get_name()}: boot image of {instance_name!r} unavailable: {e}")
            return None

    # ------------------------------------------------- packer source hooks
    def packer_source_type(self) -> str:
        from .gcp_packer_source import GOOGLECOMPUTE
        return GOOGLECOMPUTE

    def packer_source_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                             self_subconfig: Any, psi: Any, tags: dict[str, str],
                             final_name: str, pinned: str | None) -> list[str]:
        from .gcp_packer_source import googlecompute_source
        return googlecompute_source(self.model, image, runtime=runtime, source_type=source_type,
                                    subconfig=subconfig, self_subconfig=self_subconfig, psi=psi,
                                    tags=tags, final_name=final_name, pinned=pinned)

    def build_id_from_artifact(self, artifact_id: str) -> str:
        """googlecompute's manifest artifact_id is the image name itself."""
        return artifact_id


class GCPCLIVersionChecker(AbstractVersionChecker):
    """Version checker for GCP."""

    @classmethod
    def csis_name(cls) -> str:
        return GCP_RUNTIME


    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.VERSION_CHECKER


    def get_regex(self) -> str:
        # the SDK version (`Google Cloud SDK 585.0.0`, the first line), not the
        # `core` component's date-shaped version nobody quotes (stage 48.1)
        return r"Google Cloud SDK ([\d\.]+)"
