# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""AWS utility functions for EC2 and AMI queries."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import logging
from typing import Any, Sequence, cast
import boto3  # type: ignore[import-untyped]
from botocore.client import BaseClient as EC2  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError

from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig

log = logging.getLogger(__name__)

class AMINotFoundError(Exception):
    """Raised when no AMI is found matching the query."""

    pass


class AMIQueryError(Exception):
    """Raised when an AMI query fails."""

    pass


AWS_DI_MAP: dict[str, str] = {
    "executable-users": "ExecutableUsers",
    "owners": "Owners",
    "filters": "Filters",
    "image_ids": "ImageIds",
    # The image architecture ( i386 | x86_64 | arm64 | x86_64_mac | arm64_mac).
    "architecture": "architecture",
    # A Boolean value that indicates whether the Amazon EBS volume is deleted
    # on instance termination.
    "block_device_mapping.delete_on_termination": (
        "block-device-mapping.delete-on-termination"
    ),
    # The device name specified in the block device mapping
    # (for example, /dev/sdh or xvdh).
    "block_device_mapping.device_name": "block-device-mapping.device-name",
    # The ID of the snapshot used for the Amazon EBS volume.
    "block_device_mapping.snapshot_id": "block-device-mapping.snapshot-id",
    # The volume size of the Amazon EBS volume, in GiB.
    "block_device_mapping.volume_size": "block-device-mapping.volume-size",
    # The volume type of the Amazon EBS volume
    # ( io1 | io2 | gp2 | gp3 | sc1 | st1 | standard).
    "block_device_mapping.volume_type": "block-device-mapping.volume-type",
    # A Boolean that indicates whether the Amazon EBS volume is encrypted.
    "block_device_mapping.encrypted": "block-device-mapping.encrypted",
    # The time when the image was created, in the ISO 8601 format in the UTC
    # time zone (YYYY-MM-DDThh:mm:ss.sssZ), for example,
    # 2021-09-29T11:04:43.305Z. You can use a wildcard ( *), for example,
    # 2021-09-29T*, which matches an entire day.
    "creation_date": "creation-date",
    # The description of the image (provided during image creation).
    "description": "description",
    # A Boolean that indicates whether enhanced networking with ENA is enabled.
    "ena_support": "ena-support",
    # A Boolean that indicates whether this image can be used under the Amazon
    # Web Services Free Tier ( true | false).
    "free_tier_eligible": "free-tier-eligible",
    # The hypervisor type ( ovm | xen).
    "hypervisor": "hypervisor",
    # A Boolean that indicates whether the image meets the criteria specified
    # for Allowed AMIs.
    "image_allowed": "image-allowed",
    "image_id": "image-id",  # The ID of the image.
    "image_type": "image-type",  # The image type ( machine | kernel | ramdisk).
    "is_public": "is-public",  # A Boolean that indicates whether the image is public.
    "kernel_id": "kernel-id",  # The kernel ID.
    "manifest_location": "manifest-location",  # The location of the image manifest.
    "name": "name",  # The name of the AMI (provided during image creation).
    # The owner alias ( amazon | aws-backup-vault | aws-marketplace). The valid
    # aliases are defined in an Amazon-maintained list. This is not the Amazon
    # Web Services account alias that can be set using the IAM console.
    # We recommend that you use the Owner request parameter instead of this filter.
    "owner_alias": "owner-alias",
    # The Amazon Web Services account ID of the owner. We recommend that you
    # use the Owner request parameter instead of this filter.
    "owner_id": "owner-id",
    "platform": "platform",  # The platform. The only supported value is windows.
    "product_code": "product-code",  # The product code.
    # The type of the product code ( marketplace).
    "product_code.type_": "product-code.type_",
    "ramdisk_id": "ramdisk-id",  # The RAM disk ID.
    # The device name of the root device volume (for example, /dev/sda1).
    "root_device_name": "root-device-name",
    # The type of the root device volume ( ebs | instance-store).
    "root_device_type": "root-device-type",
    # The ID of the source AMI from which the AMI was created.
    "source_image_id": "source-image-id",
    "source_image_region": "source-image-region",  # The Region of the source AMI.
    # The ID of the instance that the AMI was created from if the AMI was
    # created using CreateImage. This filter is applicable only if the AMI
    # was created using CreateImage.
    "source_instance_id": "source-instance-id",
    "state": "state",  # The state of the image ( available | pending | failed).
    "state_reason_code": "state-reason-code",  # The reason code for the state change.
    "state_reason_message": "state-reason-message",  # The message for the state change.
    # A value of simple indicates that enhanced networking with the Intel
    # 82599 VF interface is enabled.
    "sriov_net_support": "sriov-net-support",
    # "tag:<key>" : "tag:<key>",
    # # The key/value combination of a tag assigned to the resource. Use the
    # # tag key in the filter name and the tag value as the filter value.
    # # For example, to find all resources that have a tag with the key Owner
    # # and the value TeamA, specify tag:Owner for the filter name and TeamA
    # # for the filter value.
    # The key of a tag assigned to the resource. Use this filter to find all
    # resources assigned a tag with a specific key, regardless of the tag value.
    "tag_key": "tag-key",
    # The virtualization type ( paravirtual | hvm).
    "virtualization_type": "virtualization-type",
}


def remap_for_image_query(rc: OSBuilderBaseImageBuilderSubconfig) -> tuple[dict[str, Any], dict[str, Any]]:
    ret: dict[str, Any] = {
        "DryRun": False,
        "IncludeDisabled": False,
        "IncludeDeprecated": False,
    }
    owners: Sequence[Any] = rc.get_owners() if rc else []
    ret["Owners"] = owners # completely overridden if specified in config
    missed: dict[str, Any] = {}
    # stage 63: a deep copy -- the loop below rewrites the filters mapping in
    # place, and get_query() hands back the entry's own nested dicts, so the
    # model's query used to be mutated by every resolution
    for topk, topv in copy.deepcopy(dict(rc.get_query())).items():
        _key2 = AWS_DI_MAP.get(topk, None)
        if not _key2:
            missed[topk] = topv
            continue
        topk = _key2
        if topk == "Owners":
            if isinstance(topv, list):
                topv = [str(i) for i in topv]
            else:
                topv = [str(topv)]
        elif topk == "Filters":
            if isinstance(topv, dict):
                topv["state"] = (
                    "available"  # Ensure we only get available images, but allow override
                )
                new_dict: dict[str, Any] = {}
                for _k, _v in topv.items():
                    _k = AWS_DI_MAP.get(_k, _k)
                    assert _k is not None, "Bad Filter key is None"
                    if _k == "Owners":
                        if isinstance(_v, list):
                            _v = [str(i) for i in _v]
                        else:
                            _v = [str(_v)]
                    if _k.startswith("tag:"):
                        _k = f"tag:{_k[4:]}"
                    if isinstance(_v, bool):
                        _v = str(_v).lower()
                    new_dict[_k] = _v
                v = new_dict
                topv = [
                    {
                        "Name": AWS_DI_MAP.get(_k, _k),
                        "Values": _v if isinstance(_v, list) else [str(_v)],
                    }
                    for _k, _v in v.items()
                ]
            else:
                raise ValueError(f"Expected 'filter' value to be a dict, got {type(topv)}")
        ret[topk] = topv
    return (ret, missed)


def query_image(
    query: dict[str, Any],
    post_query_filter: dict[str, Any] | None = None,
    session_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The newest AMI matching an EC2 ``DescribeImages`` query.

    ``query`` is what ``remap_for_image_query`` builds from an OS builder
    entry: ``Owners``, ``Filters`` (``[{"Name": ..., "Values": [...]}]``) and
    the ``DryRun``/``IncludeDisabled``/``IncludeDeprecated`` flags. Every
    match is kept that agrees with ``post_query_filter`` (a mapping of AMI
    record keys to required values); the newest by ``CreationDate`` is
    returned, or None when nothing matches. ``session_config`` is the
    runtime's boto3 session configuration and is required. A pinned
    image id does not come through here (stage 63 reads the entry's
    ``image_id`` through ``query_image_by_id``).
    """
    if not query:
        raise ValueError("Query dictionary cannot be empty")

    try:
        if not session_config:
            raise ValueError("Session configuration cannot be None or empty")
        session = boto3.Session(**session_config)

        # 2. Create the client from the custom session
        ec2_client = session.client("ec2")

    except (BotoCoreError, ClientError) as e:
        raise AMIQueryError(f"Failed to create EC2 client: {e}") from e

    results = _query_by_filters(ec2_client, query)
    # Return most recently created AMI if multiple matches
    ilist = []
    for r in results:
        if post_query_filter:
            match = True
            for k, v in post_query_filter.items():
                if r.get(k) != v:
                    match = False
                    break
            if not match:
                continue
        ilist.append(r)
    if not ilist:
        return None
    if len(ilist) > 1:
        ilist.sort(key=lambda x: x.get("CreationDate", ""), reverse=True)

    return cast(dict[str, Any], ilist[0])


def _query_by_ami_id(ec2_client: Any, ami_id: str) -> dict[str, Any] | None:
    """
    Query for an AMI by its exact ID.

    Parameters
    ----------
    ec2_client : Any
        Boto3 EC2 client instance
    ami_id : str
        The exact AMI ID to retrieve

    Returns
    -------
    dict[str, Any] | None
        The AMI details dictionary, or None if not found

    Raises
    ------
    AMIQueryError
        If the API call fails
    """
    try:
        response = ec2_client.describe_images(ImageIds=[ami_id])
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        is_not_found = "InvalidImageID.NotFound" in error_code
        is_malformed = "InvalidImageID.Malformed" in error_code
        if is_not_found or is_malformed:
            return None
        raise AMIQueryError(f"Failed to query AMI by ID: {e}") from e
    except BotoCoreError as e:
        raise AMIQueryError(f"Failed to query AMI by ID: {e}") from e

    if not response.get("Images"):
        return None

    return cast(dict[str, Any], response["Images"][0])



def _query_by_filters(ec2_client: EC2, query: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Query for an AMI using filter parameters.

    Builds EC2 filters from the query dictionary and searches for matching AMIs.
    Supports standard AMI filters and tag-based filters.

    Parameters
    ----------
    ec2_client : Any
        Boto3 EC2 client instance
    query : dict[str, Any]
        Query parameters containing filter criteria. Excludes "ami_id" and
        "ami_name" which are handled elsewhere.

    Returns
    -------
    dict[str, Any] | None
        The most recently created AMI matching all filters, or None if not found

    Raises
    ------
    AMIQueryError
        If the API call fails
    ValueError
        If no valid filters are provided
    """
    if not query:
        raise ValueError("No query filters provided")

    ilist = []
    done: bool = False
    log.debug(f"Querying for AMI with filters: {query}")
    while not done:
        log.debug(".")
        try:
            response = ec2_client.describe_images(**query)
            if response.get("Images"):
                ilist.extend(response.get("Images"))
                # pprint.pprint(response, indent=2, sort_dicts=True)
            if response.get("NextToken"):
                query["NextToken"] = response["NextToken"]
            else:
                done = True
            # images = response["Images"]
        except (ClientError, BotoCoreError) as e:
            raise AMIQueryError(f"Failed to query AMI with filters: {e}") from e
    log.info(f"Found {len(ilist)} AMIs matching filters.")
    return ilist



def ec2_client(session_config: dict[str, Any] | None) -> Any:
    """A boto3 client bound to the builder's session config; the seam the
    read-only state queries (and their tests) go through."""
    return boto3.Session(**(session_config or {})).client("ec2")


def aws_client(service: str, session_config: dict[str, Any] | None) -> Any:
    return boto3.Session(**(session_config or {})).client(service)


def get_vpc_map_and_default_vpc_id(session_config: dict[str, Any]) -> tuple[dict, str | None, dict]:
    try:
        # Prevent 'multiple values for keyword argument region_name'
        config = session_config.copy()        
        session = boto3.Session(**config)
        ec2 = session.client("ec2")

        # Fetch data in bulk
        vpcs = ec2.describe_vpcs()["Vpcs"]
        subnets = ec2.describe_subnets()["Subnets"]
        route_tables = ec2.describe_route_tables()["RouteTables"]
        
        # Moved outside loop for performance
        allsgs = {
            sg["GroupId"]: sg
            for sg in ec2.describe_security_groups()["SecurityGroups"]
        }

        vpc_map = {}
        default_vpc_id = None

        # Initialize VPC map with a flat subnets list
        for vpc in vpcs:
            v_id = vpc["VpcId"]
            vpc_map[v_id] = {"subnets": []}
            if vpc.get("IsDefault"):
                default_vpc_id = v_id

        # --- ROUTE TABLE MAPPING LOGIC ---
        subnet_to_routes = {}
        vpc_to_main_routes = {}

        for rt in route_tables:
            v_id = rt["VpcId"]
            routes = rt.get("Routes", [])
            
            for assoc in rt.get("Associations", []):
                if assoc.get("Main"):
                    vpc_to_main_routes[v_id] = routes
                
                s_id = assoc.get("SubnetId")
                if s_id:
                    subnet_to_routes[s_id] = routes

        def _is_public(routes: list) -> bool:
            for r in routes:
                gw_id = r.get("GatewayId", "")
                is_default = (r.get("DestinationCidrBlock") == "0.0.0.0/0" or 
                              r.get("DestinationIpv6CidrBlock") == "::/0")
                
                if is_default:
                    # Including both igw- and your corporate vgw- routing strategy
                    if gw_id.startswith("igw-") or gw_id.startswith("vgw-"):
                        return True
            return False

        # --- PROCESS SUBNETS ---
        for sn in subnets:
            s_id = sn["SubnetId"]
            v_id = sn["VpcId"]
            cidr = sn.get("CidrBlock")
            
            if v_id not in vpc_map:
                continue

            # Route evaluation (Specific -> Main -> Empty Fallback)
            effective_routes = subnet_to_routes.get(s_id) or vpc_to_main_routes.get(v_id, [])
            is_pub = _is_public(effective_routes)
            
            # Extract and separate requested attributes
            subnet_data = sn.copy()
            subnet_data.pop("SubnetId", None)
            subnet_data.pop("CidrBlock", None)
            
            # Pull AWS Tags list out of metadata
            aws_tags = subnet_data.pop("Tags", [])
            
            # Convert [{'Key': 'Name', 'Value': 'MySubnet'}] -> {'Name': 'MySubnet'}
            flattened_tags = {tag["Key"]: tag["Value"] for tag in aws_tags if "Key" in tag and "Value" in tag}

            # Format the subnet object exactly as specified
            formatted_subnet = {
                "subnet_id": s_id,
                "cidr": cidr,
                "is_public": is_pub,
                "tags": flattened_tags,  # Transformed into a clean dict[str, str]
                "config": subnet_data   # Stuffs all other remaining raw attributes here
            }
            
            vpc_map[v_id]["subnets"].append(formatted_subnet)

        return vpc_map, default_vpc_id, allsgs

    except (BotoCoreError, ClientError) as e:
        raise ValueError(f"AWS Error: {e}") from e#     # 1. Get all subnets in the VPC
#     subnets = ec2.describe_subnets(
#         Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
#     )['Subnets']
    
#     # 2. Get all route tables in the VPC
#     route_tables = ec2.describe_route_tables(
#         Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
#     )['RouteTables']
    
#     public_subnets = []
#     private_subnets = []

#     for subnet in subnets:
#         subnet_id = subnet['SubnetId']
#         is_public = False
        
#         # 3. Find the route table associated with this subnet
#         # Specific associations take priority over the main route table
#         specific_rt = None
#         main_rt = None
        
#         for rt in route_tables:
#             for assoc in rt.get('Associations', []):
#                 if assoc.get('SubnetId') == subnet_id:
#                     specific_rt = rt
#                     break
#                 if assoc.get('Main'):
#                     main_rt = rt
#             if specific_rt:
#                 break
        
#         # Use the specific RT if found, otherwise fall back to the Main RT
#         rt_to_check = specific_rt if specific_rt else main_rt
        
#         if rt_to_check:
#             for route in rt_to_check.get('Routes', []):
#                 # Check for a route to an Internet Gateway
#                 gateway_id = route.get('GatewayId', '')
#                 if gateway_id.startswith('igw-'):
#                     is_public = True
#                     break
        
#         if is_public:
#             public_subnets.append(subnet_id)
#         else:
#             private_subnets.append(subnet_id)

#     return public_subnets, private_subnets

