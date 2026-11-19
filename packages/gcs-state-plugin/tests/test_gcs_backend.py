# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The `gcs` backend type: its renderings, its per-root prefix,
and its place beside another kind in the collision rule."""
from __future__ import annotations

from cs_image_system.contract.state import BackendRegistration, StateLocation
from cs_image_system.gcs_state_plugin.gcs_state_models import GCS_KIND, GcsStateBuilderModel
from cs_image_system.hashicorp_utils.collector import TerraformCollector


def test_the_kind_gives_every_root_its_own_prefix_under_the_declared_one():
    settings = {"bucket": "csis-sandbox-tfstate", "prefix": "statefiles/csia"}
    assert GCS_KIND.location(settings, "gcp-pd") == StateLocation(
        type="gcs", container="csis-sandbox-tfstate", key="statefiles/csia/gcp_pd/default.tfstate")
    assert str(GCS_KIND.location(settings, "gcp-pd")) == "gcs://csis-sandbox-tfstate/statefiles/csia/gcp_pd/default.tfstate"
    assert GCS_KIND.backend_settings(settings, "gcp-pd") == {"bucket": "csis-sandbox-tfstate", "prefix": "statefiles/csia/gcp_pd"}
    assert GCS_KIND.remote_state_settings(settings, "tofu-gce") == {"bucket": "csis-sandbox-tfstate", "prefix": "statefiles/csia/tofu_gce"}
    assert GCS_KIND.backend_settings({"bucket": "b", "prefix": ""}, "ws") == {"bucket": "b", "prefix": "ws"}
    assert GCS_KIND.backend_settings({"bucket": "b", "prefix": "//a//b/"}, "ws")["prefix"] == "a/b/ws"


def test_identity_travels_as_a_path_or_an_impersonation_never_a_value():
    settings = {"bucket": "b", "prefix": "p", "credentials": "/etc/csis/gcs.json",
                "impersonate_service_account": "tf@csis-sandbox.iam.gserviceaccount.com",
                "kms_encryption_key": "projects/x/locations/y/keyRings/z/cryptoKeys/k"}
    backend = GCS_KIND.backend_settings(settings, "ws")
    assert backend["credentials"] == "/etc/csis/gcs.json" and backend["impersonate_service_account"].startswith("tf@")
    assert backend["kms_encryption_key"].endswith("/k")
    remote = GCS_KIND.remote_state_settings(settings, "ws")
    assert "kms_encryption_key" not in remote and remote["credentials"] == "/etc/csis/gcs.json"


def test_the_model_registers_the_kind_and_trims_its_prefix():
    model = GcsStateBuilderModel(name="gcs-east1", type_="gcs", bucket=" csis-sandbox-tfstate ", prefix="/statefiles/csia/")
    reg = model.to_backend_registration()
    assert reg.kind is GCS_KIND and reg.type == "gcs" and reg.settings["bucket"] == "csis-sandbox-tfstate"
    assert reg.settings["prefix"] == "statefiles/csia"
    assert model.get_state_file_path("gcp-gcs") == "statefiles/csia/gcp_gcs/default.tfstate"


def test_a_gcs_location_is_its_own_kind_of_place_in_the_collision_rule():
    # beside the core's local backend only: a family's tests name no other provider family's plugin
    from cs_image_system.local_state_plugin.local_state_models import LOCAL_KIND
    col = TerraformCollector()
    col.reset()
    try:
        col.register_backend(BackendRegistration(name="gcs", type="gcs", kind=GCS_KIND, is_default=True,
                                                 settings={"bucket": "statefiles", "prefix": "statefiles"}))
        col.register_backend(BackendRegistration(name="local", type="local", kind=LOCAL_KIND, settings={"path": "statefiles"}))
        for name in ("gcs", "local"):
            col.set_backend(f"ws-{name}", name)
        col.validate_state_locations()                                   # one name, two types: two places
        col.set_backend("ws_gcs", "gcs")                                 # collapses onto ws-gcs's object
        assert col.state_collisions(col.state_locations()) == [
            "workspaces ws-gcs, ws_gcs would share the state object gcs://statefiles/statefiles/ws_gcs/default.tfstate"]
    finally:
        col.reset()
