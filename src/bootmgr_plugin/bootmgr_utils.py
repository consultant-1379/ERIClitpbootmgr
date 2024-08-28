##############################################################################
# COPYRIGHT Ericsson AB 2022
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from litp.core.litp_logging import LitpLogger
from litp.core.future_property_value import FuturePropertyValue

log = LitpLogger()


class BootMgrUtils(object):

    @staticmethod
    def get_disk_uuid(disk):
        """
        Get the UUID of an disk or lun-disk
        """
        if disk.item_type_id == 'disk':
            uuid_prop = disk.uuid
        else:
            uuid_prop = FuturePropertyValue(disk, 'uuid')

        return uuid_prop

    @staticmethod
    def system_disks(node):
        """
        Ignore the abstract base type - only select
        instances of extensions of the base type.
        """
        if hasattr(node, 'system') and node.system:
            return [drive for drive in node.system.disks
                    if drive.item_type_id != 'disk-base']
        return []

    @staticmethod
    def get_disks_for_pds(pds, node):
        disks = []
        for disk in BootMgrUtils.system_disks(node):
            for pd in pds:
                if disk.name and (disk.name == pd.device_name):
                    disks.append(BootMgrUtils.get_disk_uuid(disk))
        return disks
