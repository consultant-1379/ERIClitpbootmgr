##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from mock import Mock

import litp.core.model_type
from litp.core.litp_logging import LitpLogger
from litp.core.task import OrderedTaskList

log = LitpLogger()


class BootMgrMock(Mock):
    def __init__(self, item_type_id, item_id):
        super(BootMgrMock, self).__init__(item_id=item_id, item_type_id=item_type_id)

        self.properties = {}
        self.applied_properties = {}
        self.property_names = []
        self.get_vpath = lambda: "/%s/%s" % (self.item_type_id, self.item_id)
        self.get_source = lambda: self
        self.item_type = litp.core.model_type.ItemType(item_type_id)

    @staticmethod
    def set_properties(item):
        for prop_name in item.property_names:
            item.properties[prop_name] = getattr(item, prop_name)

    @staticmethod
    def set_applied_properties(item):
        for prop_name in item.property_names:
            item.applied_properties[prop_name] = getattr(item, prop_name)

    @staticmethod
    def _set_state_xxx(items, state):
        for item in items:
            if not isinstance(item, BootMgrMock):
                raise Exception('Invalid Mock item', item)

            BootMgrMock.set_properties(item)

            if 'applied' == state:
                item.is_applied = lambda: True
                item.is_for_removal = lambda: False
                item.is_updated = lambda: False
                item.is_initial = lambda: False
                BootMgrMock.set_applied_properties(item)
            elif 'removed' == state:
                item.is_applied = lambda: False
                item.is_for_removal = lambda: True
                item.is_updated = lambda: False
                item.is_initial = lambda: False
            # removed will be removed and for_removal used instead
            elif 'for_removal' == state:
                item.is_applied = lambda: False
                item.is_for_removal = lambda: True
                item.is_updated = lambda: False
                item.is_initial = lambda: False
            elif 'updated' == state:
                item.is_applied = lambda: False
                item.is_for_removal = lambda: False
                item.is_updated = lambda: True
                item.is_initial = lambda: False
            elif 'initial' == state:
                item.is_applied = lambda: False
                item.is_for_removal = lambda: False
                item.is_updated = lambda: False
                item.is_initial = lambda: True

    @staticmethod
    def _set_state_applied(items):
        BootMgrMock._set_state_xxx(items, 'applied')

    @staticmethod
    def _set_state_updated(items):
        BootMgrMock._set_state_xxx(items, 'updated')

    @staticmethod
    def _set_state_initial(items):
        BootMgrMock._set_state_xxx(items, 'initial')

    @staticmethod
    def _set_state_removed(items):
        BootMgrMock._set_state_xxx(items, 'removed')

    @staticmethod
    def _set_state_for_removal(items):
        BootMgrMock._set_state_xxx(items, 'for_removal')

    @staticmethod
    def log_trace(preamble, expected, actual):

        log.trace.debug("")
        log.trace.debug("%s" % preamble)
        log.trace.debug("")

        log.trace.debug("Expected Output :")
        log.trace.debug("-----------------")
        log.trace.debug("")

        for idx, exp in enumerate(expected):
            log.trace.debug("%d. %s" % ((idx+1), exp))

        log.trace.debug("")
        log.trace.debug("Actual Output :")
        log.trace.debug("---------------")
        log.trace.debug("")

        for idx, act in enumerate(actual):
            log.trace.debug("%d. %s" % ((idx + 1), act))

        log.trace.debug("")

    @staticmethod
    def assert_validation_errors(test, expected, errors):

        preamble = "BootMgrMock.assert_validation_errors()"
        BootMgrMock.log_trace(preamble, expected, errors)

        test.assertTrue(
            len(expected) <= len(errors),
            preamble + ": number of expected errors should be "
        )

        all_present = all([e in errors for e in expected])

        test.assertTrue(
            all_present,
            preamble + ": all expected validation errors did not occur"
        )

    @staticmethod
    def __recursive_task_list_flatten(items, flattened):
        for item in items:
            if isinstance(item, OrderedTaskList):
                BootMgrMock.__recursive_task_list_flatten(
                    item.task_list, flattened
                )
            else:
                flattened.append(item)

    @staticmethod
    def flatten_tasks(tasks):
        task_list = []
        BootMgrMock.__recursive_task_list_flatten(tasks, task_list)
        return task_list

    @staticmethod
    def assert_tasks(test, expected, tasks, attr):

        preamble = "BootMgrMock.assert_tasks(attr='%s')" % attr
        flattened = BootMgrMock.flatten_tasks(tasks)

        # select the attribute we are looking for from the tasks
        attributes = [getattr(task, attr) for task in flattened]
        BootMgrMock.log_trace(preamble,expected, attributes)

        test.assertTrue(
            len(expected) <= len(attributes),
            preamble + ": number of expected errors should be"
        )

        # assert all expected responses are present
        all_present = all([e in attributes for e in expected])

        test.assertTrue(
            all_present,
            preamble + ": all expected attributes did not occur "
        )

    @staticmethod
    def assert_task_descriptions(test, expected, tasks):
        BootMgrMock.assert_tasks(
            test, expected, tasks, 'description'
        )

    @staticmethod
    def assert_task_call_types(test, expected, tasks):
        BootMgrMock.assert_tasks(
            test, expected, tasks, 'call_type'
        )

    @staticmethod
    def assert_task_kwargs(test, expected, tasks):
        BootMgrMock.assert_tasks(
            test, expected, tasks, 'kwargs'
        )


class BootMgrMockStorageProfile(BootMgrMock):
    def __init__(self, item_id, volume_driver):
        super(BootMgrMockStorageProfile, self).__init__(
            item_type_id='storage-profile',
            item_id=item_id
        )
        self.volume_driver = volume_driver
        self.get_source = lambda: self
        self.view_root_vg = ''

        self.volume_groups = []
        self.property_names = ['volume_driver']


class BootMgrMockNode(BootMgrMock):
    def __init__(self, item_id, hostname, item_type_id='node', os='rhel6'):
        super(BootMgrMockNode, self).__init__(item_type_id=item_type_id,
                                              item_id=item_id)
        self.hostname = hostname
        self.is_ms = Mock(return_value=self.item_type_id == 'ms')
        self.system = BootMgrMockSystem('mn1') if item_id != 'ms' else None
        self.storage_profile = None
        self.property_names = ['hostname']
        self.get_cluster = lambda: None
        self.network_interfaces = []
        self.os = BootMgrMockOs('ms', os)

class BootMgrMockMS(BootMgrMockNode):
    def __init__(self):
        super(BootMgrMockMS, self).__init__(item_id='ms',
                                           hostname='ms1',
                                           item_type_id='ms')

class BootMgrMockSystem(BootMgrMock):
    def __init__(self, item_id, boot_mode='bios'):
        super(BootMgrMockSystem, self).__init__(item_type_id='system',
                                               item_id=item_id)
        self.disks = []
        self.boot_mode = boot_mode

class BootMgrMockOs(BootMgrMock):
    def __init__(self, item_id, version, item_type_id='os-profile'):
        super(BootMgrMockOs, self).__init__(
            item_type_id=item_type_id,
            item_id=item_id)
        self.version = version

class BootMgrMockDisk(BootMgrMock):
    def __init__(self, item_id, name, size, uuid, bootable,
                 item_type_id='disk'):
        super(BootMgrMockDisk, self).__init__(
            item_type_id=item_type_id, item_id=item_id
        )

        self.name = name
        self.size = size
        self.uuid = uuid
        self.bootable = bootable
        self.disk_part = 'false'
        self.disk_fact_name = '$::disk_abcd_dev'
        self.disk_group = 'dg'

        self.property_names = ['name', 'size', 'uuid', 'bootable', 'disk_part']



class BootMgrMockContext(BootMgrMock):
    def __init__(self):
        super(BootMgrMockContext, self).__init__(item_type_id='', item_id='')
        self.rpc_command = None
        self.snapshot_name = None
        self.snapshot_object = None

    def snapshot_model(self):
        return None

    def snapshot_action(self):
        return None

    def query(self, item_type_id):
        return []

class BootMgrMockCluster(BootMgrMock):
    def __init__(self, item_id, cluster_type='', item_type_id='cluster'):
        super(BootMgrMockCluster, self).__init__(
            item_type_id=item_type_id, item_id=item_id
        )

        self.cluster_type = cluster_type
        self.cluster_id = item_id
        self.property_names = ['cluster_type']

        # these are all collections
        self.storage_profile = []
        self.software = []
        self.nodes = []
        self.services = []
        self.software = []
