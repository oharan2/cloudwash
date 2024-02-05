"""ec2 CR Cleanup Utilities"""
from botocore.client import ClientError

from cloudwash.client import compute_client
from cloudwash.config import settings
from cloudwash.logger import logger
from cloudwash.utils import dry_data
from cloudwash.utils import echo_dry
from cloudwash.utils import total_running_time
from cloudwash.utils import delete_ocp

EC2_OCP_TAG = "tag.key:kubernetes.io/cluster/*"
EC2_INSTANCE_FILTER = "resourcetype:ec2:instance"

def cleanup(**kwargs):
    is_dry_run = kwargs["dry_run"]
    data = ['VMS', 'DISCS', 'PIPS', 'RESOURCES']
    regions = settings.providers.ec2.regions
    with compute_client("ec2", ec2_region="us-west-2") as client:
        if "all" in regions:
            regions = client.list_regions()
    regions = ["ap-south-1","us-east-1","us-east-2"]  # Aggregator index # TODO remove
    for region in regions:
        dry_data['VMS']['stop'] = []
        dry_data['VMS']['skip'] = []
        dry_data["OCPS"]["delete"] = []
        for items in data:
            dry_data[items]['delete'] = []
        with compute_client("ec2", ec2_region=region) as ec2_client:
            # Dry Data Collection Defs
            def dry_vms():
                all_vms = ec2_client.list_vms()
                for vm in all_vms:
                    if vm.name in settings.providers.ec2.except_vm_list:
                        dry_data["VMS"]["skip"].append(vm.name)
                        continue
                    elif total_running_time(vm).minutes >= settings.sla_minutes:
                        if vm.name in settings.providers.ec2.except_vm_stop_list:
                            dry_data["VMS"]["stop"].append(vm.name)
                            continue
                        elif vm.name.startswith(settings.delete_vm):
                            dry_data["VMS"]["delete"].append(vm.name)
                return dry_data["VMS"]

            def dry_nics():
                rnics = ec2_client.get_all_unused_network_interfaces()
                [dry_data["NICS"]["delete"].append(dnic["NetworkInterfaceId"]) for dnic in rnics]
                return dry_data["NICS"]["delete"]

            def dry_discs():
                rdiscs = ec2_client.get_all_unattached_volumes()
                [dry_data["DISCS"]["delete"].append(ddisc["VolumeId"]) for ddisc in rdiscs]
                return dry_data["DISCS"]["delete"]

            def dry_pips():
                rpips = ec2_client.get_all_disassociated_addresses()
                [dry_data["PIPS"]["delete"].append(dpip["AllocationId"]) for dpip in rpips]
                return dry_data["PIPS"]["delete"]

            def dry_ocps():
                """
                Obtains list of available resources using AWS ResourceExplorer(resource-explorer-2). For each
                resource associated with the ocp tag; if it's an EC2 instance, we'll work with instance CreationTime
                stamp, otherwise this resource will be considered as a leftover (not associated with an OCP cluster).
                """
                # TODO botocore.errorfactory.UnauthorizedException:
                # An error occurred (UnauthorizedException) when calling the Search operation: Unauthorized
                # https://docs.aws.amazon.com/resource-explorer/latest/userguide/troubleshooting_search.html#:~:text=The%20Region%20with%20the%20resource%20doesn%27t%20have%20Resource%20Explorer%20turned%20on
                time_ref = "{}m".format(settings.sla_minutes)
                query = " ".join([EC2_OCP_TAG, EC2_INSTANCE_FILTER, "region:{}".format(region)])
                import ipdb
                ipdb.set_trace()
                all_ocps = ec2_client.list_resources(query=query)
                if isinstance(all_ocps,ClientError):
                    logger.info(f"Region {region} is Unauthorized")
                    return dry_data["OCPS"]["delete"]

                print(len(all_ocps))
                # filtered_ec2_instances = ec2_client.list_resources(query=query, time_ref=time_ref)

                # FROM CSPI cloud-tools
                #  for conn in ec2_client(region_name=region_name).describe_vpc_peering_connections()["VpcPeeringConnections"]:

                for ocp in all_ocps:
                    dry_data["OCPS"]["delete"].append(ocp)
                return dry_data["OCPS"]["delete"]

            # Remove / Stop VMs
            def remove_vms(avms):
                # Remove VMs
                [ec2_client.get_vm(vm_name).delete() for vm_name in avms["delete"]]
                # Stop VMs
                [ec2_client.get_vm(vm_name).stop() for vm_name in avms["stop"]]

            # Actual Cleaning and dry execution
            logger.info(f"\nResources from the region: {region}")
            if kwargs["vms"] or kwargs["_all"]:
                avms = dry_vms()
                if not is_dry_run:
                    remove_vms(avms=avms)
                    logger.info(f"Stopped VMs: \n{avms['stop']}")
                    logger.info(f"Removed VMs: \n{avms['delete']}")
                    logger.info(f"Skipped VMs: \n{avms['skip']}")
            if kwargs["nics"] or kwargs["_all"]:
                rnics = dry_nics()
                if not is_dry_run:
                    ec2_client.remove_all_unused_nics()
                    logger.info(f"Removed NICs: \n{rnics}")
            if kwargs["discs"] or kwargs["_all"]:
                rdiscs = dry_discs()
                if not is_dry_run:
                    ec2_client.remove_all_unused_volumes()
                    logger.info(f"Removed Discs: \n{rdiscs}")
            if kwargs["pips"] or kwargs["_all"]:
                rpips = dry_pips()
                if not is_dry_run:
                    ec2_client.remove_all_unused_ips()
                    logger.info(f"Removed PIPs: \n{rpips}")
            if kwargs["ocps"]:
                rocps = dry_ocps()
                if not is_dry_run:
                    for ocp in rocps:
                        delete_ocp(ocp)
                    ocp_names = [ocp["name"] for ocp in rocps]
                    logger.info(f"[WIP] Removed OCP clusters: \n{ocp_names}")
            if is_dry_run:
                echo_dry(dry_data)
