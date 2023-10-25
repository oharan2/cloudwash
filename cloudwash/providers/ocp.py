# """ec2 CR Cleanup Utilities"""
# from cloudwash.client import compute_client
# from cloudwash.config import settings
# from cloudwash.logger import logger
# from cloudwash.utils import dry_data
# from cloudwash.utils import echo_dry
# from cloudwash.utils import total_running_time


def cleanup(**kwargs):

    is_dry_run = kwargs["dry_run"]
    # IAM_client, EC2_client
    data = ['VPC', 'NICS', 'DISCS', 'PIPS', 'RESOURCES', 'STACKS']
