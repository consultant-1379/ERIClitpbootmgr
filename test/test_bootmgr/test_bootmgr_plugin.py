import unittest

from mock import Mock, MagicMock, patch, call

import re
import time
import os

from bootmgr_plugin import bootmgr_plugin
from bootmgr_extension.bootmgr_extension import BootManagerExtension

from litp.core.model_manager import ModelManager
from litp.core.model_manager import ModelItem
from litp.core.plugin_context_api import PluginApiContext
from litp.core.execution_manager import (CallbackExecutionException,
                                         PlanStoppedException)
from litp.core.validators import ValidationError
from litp.extensions.core_extension import CoreExtension

from network_extension.network_extension import NetworkExtension
from volmgr_extension.volmgr_extension import VolMgrExtension
from libvirt_extension.libvirt_extension import LibvirtExtension
from yum_extension.yum_extension import YumExtension

from mock_boot_items import (
    BootMgrMock,
    BootMgrMockNode,
    BootMgrMockMS,
    BootMgrMockCluster,
    BootMgrMockDisk,
    BootMgrMockSystem,
    BootMgrMockContext,
    BootMgrMockStorageProfile,
    BootMgrMockOs
)


class BootManagerPluginTest(unittest.TestCase):
    interface_name_regex = re.compile(r"^([a-zA-Z]+)\d*.*")

    def setUp(self):

        self.testClass = bootmgr_plugin.BootManagerPlugin()
        self.model = ModelManager()
        core = CoreExtension()
        bootmgr_ext = BootManagerExtension()
        networking = NetworkExtension()
        self.api = PluginApiContext(self.model)
        self.testClass.token = "TOKEN"

        self.testClass._check_node = lambda node, boot_network: True

        self.model.register_property_types(core.define_property_types())
        self.model.register_item_types(core.define_item_types())
        self.model.register_property_types(bootmgr_ext.define_property_types())
        self.model.register_item_types(bootmgr_ext.define_item_types())
        self.model.register_property_types(networking.define_property_types())
        self.model.register_item_types(networking.define_item_types())

        self.model.register_property_types(
            self.testClass.register_property_types())
        self.model.register_item_types(self.testClass.register_item_types())

        self.model.register_property_types(
            VolMgrExtension().define_property_types())
        self.model.register_item_types(VolMgrExtension().define_item_types())

        self.model.register_property_types(
            YumExtension().define_property_types())
        self.model.register_item_types(YumExtension().define_item_types())
        # needed to validate system names in libvirt envs
        self.model.register_property_types(
            LibvirtExtension().define_property_types())
        self.model.register_item_types(LibvirtExtension().define_item_types())

        # Create root items
        self.model.create_core_root_items()

        items = {}

        for i in [1, 2]:
            path = "/infrastructure/systems/system%d" % i
            items[path] = self.model.create_item(
                "system", path, system_name='MN%dVM' % i
            )

        # create disks for system 1
        uuid1 = "0x5000c50035ca73fe"
        uuid2 = "0x500fe114da65e700"

        # create disks for system 2
        uuid3 = "0x5000c50035ca73ff"
        uuid4 = "0x500fe114da65e701"

        path = "/infrastructure/systems/system1/disks/local0"
        items[path] = self.model.create_item(
            "disk", path, name="hd0", size="20G", bootable="true", uuid=uuid1
        )

        path = "/infrastructure/systems/system1/disks/local1"
        items[path] = self.model.create_item(
            "disk", path,
            name="secondary", size="18G", bootable="false", uuid=uuid2
        )

        path = "/infrastructure/systems/system2/disks/local0"
        items[path] = self.model.create_item(
            "disk", path, name="hd0", size="20G", bootable="true", uuid=uuid3
        )

        path = "/infrastructure/systems/system2/disks/local1"
        items[path] = self.model.create_item(
            "disk", path,
            name="secondary", size="18G", bootable="false", uuid=uuid4
        )

        self.all_disk_uuids = [uuid1, uuid2, uuid3, uuid4]

        # Create cobbler service item
        path = "/ms/services/cobbler"
        items[path] = self.model.create_item(
            "cobbler-service", path, pxe_boot_timeout=600
        )

        path = "/deployments/d1"
        items[path] = self.model.create_item("deployment", path)

        path = "/deployments/d1/clusters/c1"
        items[path] = self.model.create_item("cluster", path)

        path = "/infrastructure/networking/networks/mgmt"
        items[path] = self.model.create_item(
            "network", path,
            name='nodes', subnet='10.10.10.0/24', litp_management='true'
        )

        path = "/infrastructure/networking/networks/net2"
        items[path] = self.model.create_item(
            "network", path, name='net2', subnet='10.20.10.0/24'
        )

        path = "/infrastructure/networking/networks/hb1"
        items[path] = self.model.create_item("network", path, name='hb1')

        path = "/ms/network_interfaces/nic0"
        items[path] = self.model.create_item(
            'eth', path,
            device_name='eth0', ipaddress='10.0.0.5',
            macaddress='aa:bb:cc:dd:ee:f1', network_name='nodes'
        )

        path = "/ms/network_interfaces/nic1"
        items[path] = self.model.create_item(
            'eth', path, device_name='eth1',
            macaddress='aa:bb:cc:dd:ee:f1', network_name='hb1'
        )

        path = "/software/profiles/rhel_6_2"
        items[path] = self.model.create_item(
            "os-profile", path, name='rhel', path='/tmp/'
        )

        path = "/infrastructure/networking/routes/r1"
        items[path] = self.model.create_item(
            "route", path, subnet="0.0.0.0/0", gateway="10.46.23.254"
        )

        path = "/infrastructure/storage/storage_profiles/sp"
        items[path] = self.model.create_item("storage-profile", path)

        path = ("/infrastructure/storage/storage_profiles/sp/"
                "volume_groups/vg_root")
        items[path] = self.model.create_item(
            "volume-group", path, volume_group_name="vg_root"
        )

        # link node to the actual disks
        path = ("/infrastructure/storage/storage_profiles/sp/volume_groups/"
                "vg_root/physical_devices/pd1")
        items[path] = self.model.create_item(
            "physical-device", path, device_name="hd0"
        )

        path = ("/infrastructure/storage/storage_profiles/sp/volume_groups/"
                "vg_root/physical_devices/pd2")
        items[path] = self.model.create_item(
            "physical-device", path, device_name="secondary"
        )

        path = ("/infrastructure/storage/storage_profiles/sp/volume_groups/"
                "vg_root/file_systems/root")
        items[path] = self.model.create_item(
            "file-system", path, size="10G", mount_point="/", type="ext4"
        )

        path = ("/infrastructure/storage/storage_profiles/sp/volume_groups/"
                "vg_root/file_systems/swap")
        items[path] = self.model.create_item(
            "file-system", path, size="3G", mount_point="swap", type="swap"
        )

        node_data = {
            1: ('08:00:27:5B:C1:3F', '10.46.23.1'),
            2: ('08:00:27:5B:C1:3A', '10.46.23.2')
        }

        for idx, value in node_data.iteritems():
            path = "/deployments/d1/clusters/c1/nodes/n%d" % idx
            items[path] = self.model.create_item(
                "node", path, hostname='n%d' % idx
            )
            path = "/deployments/d1/clusters/c1/nodes/n%d/system" % idx
            items[path] = self.model.create_inherited(
                "/infrastructure/systems/system%d" % idx, path
            )
            path = "/deployments/d1/clusters/c1/nodes/n%d/os" % idx
            items[path] = self.model.create_inherited(
                "/software/profiles/rhel_6_2", path
            )
            path = "/deployments/d1/clusters/c1/nodes/n%d/routes/r1" % idx
            items[path] = self.model.create_inherited(
                "/infrastructure/networking/routes/r1", path
            )

            # set up nics
            path = ("/deployments/d1/clusters/c1/nodes/n%d/"
                    "network_interfaces/nic0") % idx
            mac, ip = value
            items[path] = self.model.create_item(
                "eth", path,
                device_name='eth0', macaddress=mac,
                network_name='nodes', ipaddress=ip
            )

            # inherit storage profile to the node
            path = ("/deployments/d1/clusters/c1/"
                    "nodes/n%d/storage_profile") % idx
            items[path] = self.model.create_inherited(
                "/infrastructure/storage/storage_profiles/sp", path
            )

        for path, item in items.iteritems():
            self.assertTrue(
                isinstance(item, ModelItem),
                "BootManagerPluginTest.setUp() failed to create model item "
                "'%s', got '%s' instead of ModelItem" % (path, item)
            )

        self.mock_callback_api = MagicMock()

        self.partition_snippets_dir = os.path.join(os.path.dirname(
            __file__), 'test_snippets', 'partition_snippets')

    def tearDown(self):
        reload(bootmgr_plugin)

    def test_validate_system_exists(self):
        node = self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node3", hostname='node3'
        )
        self.assertTrue(isinstance(node, ModelItem))
        nodes = self.testClass._nodes_in_the_deployment(self.api)
        errors = self.testClass._validate_system_exists(nodes)
        self.assertTrue(len(errors) == 1)
        self.assertEqual(ValidationError, type(errors[0]))

    def test_validate_system_exists_for_removal(self):
        no_system_node = self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node3", hostname='node3'
        )
        self.assertTrue(isinstance(no_system_node, ModelItem))
        no_system_node.set_for_removal()
        nodes = self.testClass._nodes_in_the_deployment(self.api)
        errors = self.testClass._validate_system_exists(nodes)
        self.assertEqual([], errors)
        self.testClass.create_configuration(self.api)

    def test_create_configuration(self):
        tasks = self.testClass.create_configuration(self.api)
        os_version = self.api.query("os-profile")[0].version

        expected = [
            'Import "{0}" distro "rhel-x86_64"'.format(os_version.upper()),
            'Add "{0}" profile "rhel-x86_64"'.format(os_version.upper()),
            'Register system "n2" for install',
            'Register system "n1" for install',
            'Wait for node "n2" to PXE boot',
            'Wait for node "n1" to PXE boot',
        ]

        BootMgrMock.assert_task_descriptions(self, expected, tasks)

    def test__get_boot_network(self):
        boot_net = self.testClass._get_boot_network(self.api)
        self.assertEqual("nodes", boot_net.name)

    def test__get_system_disk(self):
        # Because get_system_disk will return None if no disk is found
        disks = [self.testClass._get_system_disk(node)
                 for node in self.api.query("node")]

        self.assertFalse(None in disks)
        self.assertEqual(2, len(disks))

    def test_add_udev_network_tasks(self):

        # we expect one task per each node in the deployment
        tasks = []

        self.testClass._add_udev_network_tasks(
            self.api.query("ms")[0], tasks, self.api.query("node"),
            self.api, self.api.query("cobbler-service")[0]
        )

        ct1 = MagicMock(
            call_id="n1",
            kwargs={
                'network_cards': [{'mac': '08:00:27:5b:c1:3f', 'dev': 'eth0'}]
            }
        )
        ct2 = MagicMock(
            call_id="n2",
            kwargs={
                'network_cards': [{'mac': '08:00:27:5b:c1:3a', 'dev': 'eth0'}]
            }
        )

        expected_tasks = {'n1': ct1, 'n2': ct2}

        for task in tasks:
            self.assertEqual(
                expected_tasks[task.call_id].kwargs['network_cards'],
                task.kwargs['network_cards'])

    def test_get_bridge_matching_nic_eth(self):

        bridge_interface = MagicMock(device_name="br0")
        n1_bridge = MagicMock(device_name='br0', item_type_id='bridge')
        n1_eth = MagicMock(
            device_name='eth0', item_type_id='eth',
            macaddress='11:22:33:44:55:66', bridge='br0'
        )

        node = MagicMock(
            hostname="node1", network_interfaces=[n1_bridge, n1_eth]
        )

        nic = self.testClass._get_bridge_matching_nic(node, bridge_interface)
        self.assertEqual(nic.device_name, "eth0")

    def test_get_bridge_matching_nic_bond(self):

        bridge_interface = MagicMock(device_name="br0")
        n1_bridge = MagicMock(device_name='br0', item_type_id='bridge')
        n1_bond = MagicMock(device_name='bond0', item_type_id='bond',
                            bridge='br0')
        n1_eth = MagicMock(device_name='eth0', item_type_id='eth',
                           master='bond0', is_removed=lambda: False,
                           is_for_removal=lambda: False,
                           macaddress='11:22:33:44:55:66')

        node = MagicMock(
            hostname="node1", query=lambda x: [n1_eth],
            network_interfaces=[n1_bridge, n1_bond, n1_eth]
        )

        nic = self.testClass._get_bridge_matching_nic(node, bridge_interface)
        self.assertEqual(nic.device_name, "eth0")

    def test_get_bridge_matching_nic_vlan_on_eth(self):

        bridge_interface = MagicMock(device_name="br0")
        n1_bridge = MagicMock(device_name='br0', item_type_id='bridge')
        n1_vlan = MagicMock(device_name='eth0.835', item_type_id='vlan',
                            bridge='br0')
        n1_eth = MagicMock(device_name='eth0', item_type_id='eth',
                           is_removed=lambda: False,
                           is_for_removal=lambda: False,
                           macaddress='11:22:33:44:55:66')

        node = MagicMock(
            hostname="node1", query=lambda x: [n1_eth],
            network_interfaces=[n1_bridge, n1_vlan, n1_eth]
        )

        nic = self.testClass._get_bridge_matching_nic(node, bridge_interface)
        self.assertEqual(nic.device_name, "eth0")

    def test_get_bridge_matching_nic_vlan_on_bridge(self):

        bridge_interface = MagicMock(device_name="br0")
        n1_bridge = MagicMock(device_name='br0', item_type_id='bridge')
        n1_vlan = MagicMock(
            device_name='bond0.835', item_type_id='vlan', bridge='br0'
        )
        n1_bond = MagicMock(device_name='bond0', item_type_id='bond')
        n1_eth = MagicMock(
            device_name='eth0', item_type_id='eth', master='bond0',
            is_removed=lambda: False, is_for_removal=lambda: False,
            macaddress='11:22:33:44:55:66'
        )

        node = MagicMock(
            hostname="node1", query=lambda x: [n1_eth],
            network_interfaces=[n1_bridge, n1_vlan, n1_bond, n1_eth]
        )

        nic = self.testClass._get_bridge_matching_nic(node, bridge_interface)
        self.assertEqual(nic.device_name, "eth0")

    def test_add_udev_network_tasks_management_bond(self):

        # we expect one task per each node in the deployment
        tasks = []

        node1_bond = MagicMock(
            device_name='bond0',
            item_type_id='bond',
            network_name='mgmt',
            is_removed=lambda: False,
            is_for_removal=lambda: False
        )

        node1_eth = MagicMock(
            device_name='eth0',
            macaddress='11:22:33:44:55:66',
            item_type_id='eth',
            master='bond0',
            is_removed=lambda: False,
            is_for_removal=lambda: False
        )

        nodes = [
            MagicMock(
                hostname="node1",
                network_interfaces=[node1_bond, node1_eth],
                query=lambda x: [node1_eth]
            )
        ]

        boot_network = MagicMock()
        boot_network.name = 'mgmt'
        boot_network.is_removed = lambda: False
        boot_network.is_for_removal = lambda: False

        api = MagicMock(
            query=lambda x, litp_management: [boot_network]
        )

        self.testClass._add_udev_network_tasks(
            self.api.query("ms")[0], tasks, nodes, api,
            self.api.query("cobbler-service")[0]
        )

        ct1 = MagicMock(
            call_id="node1",
            kwargs={
                'network_cards': [{'mac': '11:22:33:44:55:66', 'dev': 'eth0'}]
            }
        )

        expected_tasks = {'node1': ct1}

        for task in tasks:
            self.assertEqual(
                expected_tasks[task.call_id].kwargs['network_cards'],
                task.kwargs['network_cards']
            )

    def test_add_udev_pxe_boot_only_nic(self):

        # we expect one task per each node in the deployment
        tasks = []

        node1_eth0 = MagicMock(
            device_name='eth0',
            pxe_boot_only='true',
            macaddress='11:22:33:44:55:66',
            item_type_id='eth',
            is_removed=lambda: False,
            is_for_removal=lambda: False
        )

        node1_eth1 = MagicMock(
            device_name='eth1',
            macaddress='11:22:33:44:55:77',
            network_name='mgmt',
            item_type_id='eth',
            is_removed=lambda: False,
            is_for_removal=lambda: False
        )

        nodes = [
            MagicMock(
                hostname="node1",
                network_interfaces=[node1_eth0, node1_eth1],
                query=lambda x: [node1_eth0, node1_eth1]
            )
        ]

        boot_network = MagicMock()
        boot_network.name = 'mgmt'
        boot_network.is_removed = lambda: False
        boot_network.is_for_removal = lambda: False

        api = MagicMock(
            query=lambda x, litp_management: [boot_network]
        )

        self.testClass._add_udev_network_tasks(
            self.api.query("ms")[0], tasks, nodes, api,
            self.api.query("cobbler-service")[0]
        )

        ct1 = MagicMock(
            call_id="node1",
            kwargs={
                'network_cards': [{'mac': '11:22:33:44:55:66', 'dev': 'eth0'},
                                  {'mac': '11:22:33:44:55:77', 'dev': 'eth1'}]
            }
        )

        expected_tasks = {'node1': ct1}

        for task in tasks:
            self.assertEqual(
                expected_tasks[task.call_id].kwargs['network_cards'],
                task.kwargs['network_cards']
            )

    def test_generate_lvm_kickstart(self):

        nodes = self.api.query("node", hostname="n1")
        services = self.api.query("cobbler-service")

        self.assertEqual(1, len(services))
        service = services[0]

        tasks = []
        self.testClass._generate_lvm_kickstart(tasks, nodes[0], service)

        self.assertEqual(1, len(tasks))
        self.assertEqual((), tasks[0].args)
        self.assertEqual(
            "/var/lib/cobbler/snippets/n1.ks.partition.snippet",
            tasks[0].kwargs["path"]
        )

    def test__new_ms_network_status(self):
        context = MagicMock()
        ms = MagicMock()
        nic1 = MagicMock()
        nic2 = MagicMock()
        nic1.network_name = 'mgmt'
        nic2.network_name = 'test'
        network1 = MagicMock()
        network2 = MagicMock()
        network1.litp_management = 'true'
        network2.litp_management = 'false'
        network1.name = 'mgmt'
        network2.name = 'test'
        nic1.get_state = MagicMock(return_value='Updated')
        nic2.get_state = MagicMock(return_value='Updated')
        context.query = MagicMock(return_value=[network1, network2])
        self.testClass._new_states = ['Updated']
        ms.network_interfaces = [nic1, nic2]
        result = self.testClass._new_ms_network_status(context, ms)
        self.assertTrue(result)
        ms.network_interfaces = [nic2]
        result = self.testClass._new_ms_network_status(context, ms)
        self.assertFalse(result)

    def _extract_partition_snippet_from_tasks(self, tasks):
        self.assertEquals(1, len(tasks))
        self.assertTrue(hasattr(tasks[0], 'kwargs'))
        self.assertTrue(tasks[0].kwargs.has_key('node_hostname'))
        self.assertTrue(tasks[0].kwargs.has_key('os_version'))
        if tasks[0].kwargs['os_version'] == "rhel6":
            config_list = self.testClass._get_lvm_kickstart_config_rhel6(
                self.mock_callback_api,
                tasks[0].kwargs['node_hostname'])
        else:
            config_list = self.testClass._get_lvm_kickstart_config(
                self.mock_callback_api,
                tasks[0].kwargs['node_hostname'], tasks[0].kwargs['boot_mode'])
        self.assertTrue(isinstance(config_list, list))
        return '\n'.join(config_list)

    def _setup_mock_nodes(self, os_version="rhel7"):
        service = Mock(get_state=lambda: 'Initial')

        disk1 = BootMgrMockDisk('disk1', 'hd0', '500G', 'DEFEC8EDCAFE', 'true')
        disk2 = BootMgrMockDisk('disk2', 'hd0', '20480M', 'defec8edcafe',
                                'true')
        disk3 = BootMgrMockDisk('disk3', 'hd0', '4T', 'DeFec8EFCafE', 'true')

        self.all_disk_uuids = [disk1.uuid, disk2.uuid, disk3.uuid]

        storage_profile = BootMgrMockStorageProfile('rvg', 'lvm')

        vg_root = Mock(volume_group_name='vg_root', item_id='rvg')
        vg_root.physical_devices = [Mock(device_name='hd0')]
        vg_root.file_systems = [Mock(mount_point='/', type='ext4', size='40G',
                                     item_id='root',
                                     get_vpath=lambda: '/foo/hda')]

        storage_profile.volume_groups = [vg_root]
        storage_profile.view_root_vg = 'vg_root'
        node1 = BootMgrMockNode(item_id='n1', hostname='node1')
        node1.os.version = os_version
        node1.storage_profile = storage_profile
        node1.get_vpath = Mock(
            get_vpath=lambda: '/deployments/d1/clusters/c1/nodes/n1')
        node2 = BootMgrMockNode(item_id='n2', hostname='node2')
        node2.os.version = os_version
        node2.storage_profile = storage_profile
        node2.get_vpath = Mock(
            get_vpath=lambda: '/deployments/d1/clusters/c1/nodes/n2')
        node3 = BootMgrMockNode(item_id='n3', hostname='node3')
        node3.os.version = os_version
        node3.get_vpath = Mock(
            get_vpath=lambda: '/deployments/d1/clusters/c1/nodes/n3')
        node3.storage_profile = storage_profile
        node1.system.disks.append(disk1)
        node2.system.disks.append(disk2)
        node3.system.disks.append(disk3)

        nodes = [node1, node2, node3]
        return nodes, service, self.all_disk_uuids

    def assert_snippet_by_line(self, expected, snippet):
        expected_snippet_by_lines = expected.split("\n")
        snippet_by_lines = snippet.split("\n")
        for line in snippet_by_lines:
            self.assertEquals(expected_snippet_by_lines[
                                  snippet_by_lines.index(line)], line)

    def test_get_rhel6_disk_config(self):
        nodes, service, all_uuids = self._setup_mock_nodes(os_version="rhel6")
        tasks = []
        node = nodes[0]
        self.mock_callback_api.query.return_value = nodes
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._uuid_on_disk.return_value = True
        self.testClass._generate_lvm_kickstart(tasks, node, service)
        config = ["config starts with this string "]
        boot_part_commands = ["boot_part_commands starts with this string "]

        config, boot_part_commands = self.testClass._get_rhel6_disk_config(
            self.mock_callback_api, node.system.disks[0], config,
            boot_part_commands)
        expected_config = [
            'config starts with this string ',
            'disk_list_item=\\$(shopt -s '
            'nocaseglob; ls /dev/disk/by-id/scsi*DEFEC8EDCAFE)',
            'if [ ! -n "$disk_list_item" ]; then\ndisk_list_item=\\$(shopt -s '
            'nocaseglob; ls /dev/disk/by-id/cciss*DEFEC8EDCAFE)\nfi',
            'disk_list["disk1"]=\\$disk_list_item',
            '\nif [[ ! -b \\${disk_list["disk1"]} ]]; then\necho "ERROR: '
            'Could not find disk of UUID \'DEFEC8EDCAFE\'" >>'
            ' /dev/tty1;\nread;\nexit 1;\nfi',
            'drive_dev=\\$(basename \\$(find /dev/disk/by-id -iname '
            'scsi\\*DEFEC8EDCAFE -printf "%l"))',
            'if [ ! -n "$drive_dev" ]; then\ndrive_dev=\\$(basename \\$(find '
            '/dev/disk/by-id -iname cciss\\*DEFEC8EDCAFE -printf "%l"))\nfi',
            'clearpart_devs=\\${clearpart_devs},\\${drive_dev}']
        expected_boot_part_commands = [
            'boot_part_commands starts with this string ',
            'echo "part /boot --fstype=ext4 --size=500 --ondisk=${disk_list'
            '["disk1"]}" >>/tmp/partitioninfo']

        self.assertEqual(config, expected_config)
        self.assertEqual(boot_part_commands, expected_boot_part_commands)

    def test_partition_snippet_matches_devices_case_insensitive(self):
        nodes, service, all_uuids = self._setup_mock_nodes()

        # Node1
        tasks = []
        node1_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node1.test_partition_snippet_matches_devices_case_insensitive.snippet')
        expected_snippet_1 = open(node1_part_snippet).read().strip()
        node1 = nodes[0]
        self.mock_callback_api.query.return_value = [node1]
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._generate_lvm_kickstart(tasks, node1, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)

        self.assert_snippet_by_line(expected_snippet_1, snippet)
        self.assertEquals(expected_snippet_1, snippet)

        # Node2
        node2_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node2.test_partition_snippet_matches_devices_case_insensitive.snippet')
        expected_snippet_2 = open(node2_part_snippet).read().strip()
        expected_snippet_by_lines = expected_snippet_2.split("\n")

        tasks = []
        node2 = nodes[1]
        self.mock_callback_api.query.return_value = [node2]
        self.testClass._generate_lvm_kickstart(tasks, node2, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)

        self.assert_snippet_by_line(expected_snippet_2, snippet)
        self.assertEquals(expected_snippet_2, snippet)

        # Node 3
        node3_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node3.test_partition_snippet_matches_devices_case_insensitive.snippet')
        expected_snippet_3 = open(node3_part_snippet).read().strip()

        tasks = []
        node3 = nodes[2]
        self.mock_callback_api.query.return_value = [node3]
        self.testClass._generate_lvm_kickstart(tasks, node3, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)

        self.assert_snippet_by_line(expected_snippet_3, snippet)
        self.assertEquals(expected_snippet_3, snippet)

    def test_partition_snippet_matches_devices_case_insensitive_uefi(self):
        nodes, service, all_uuids = self._setup_mock_nodes()
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)

        # Node1
        tasks = []
        node1 = nodes[0]
        service.boot_mode = 'uefi'
        node1_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node1.test_partition_snippet_matches_devices_case_insensitive_uefi.snippet')
        expected_snippet_1 = open(node1_part_snippet).read().strip()
        self.mock_callback_api.query.return_value = [node1]
        self.testClass._generate_lvm_kickstart(tasks, node1, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assert_snippet_by_line(expected_snippet_1, snippet)
        self.assertEquals(expected_snippet_1, snippet)

        # Node2
        tasks = []
        node2 = nodes[1]
        service.boot_mode = 'uefi'
        node2_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node2.test_partition_snippet_matches_devices_case_insensitive_uefi.snippet')
        expected_snippet_2 = open(node2_part_snippet).read().strip()
        self.mock_callback_api.query.return_value = [node2]
        self.testClass._generate_lvm_kickstart(tasks, node2, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assert_snippet_by_line(expected_snippet_2, snippet)
        self.assertEquals(expected_snippet_2, snippet)

        # Node 3
        tasks = []
        node3 = nodes[2]
        service.boot_mode = 'uefi'
        node3_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node3.test_partition_snippet_matches_devices_case_insensitive_uefi.snippet')
        expected_snippet_3 = open(node3_part_snippet).read().strip()
        self.mock_callback_api.query.return_value = [node3]
        self.testClass._generate_lvm_kickstart(tasks, node3, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assert_snippet_by_line(expected_snippet_3, snippet)
        self.assertEquals(expected_snippet_3, snippet)

    def test_partition_snippet_matches_devices_case_insensitive_rhel6(self):
        nodes, service, all_uuids = self._setup_mock_nodes(os_version="rhel6")
        tasks = []

        expected_snippet = r'''
# Hash map
declare -A disk_list
# Loop through the data structure we have been passed in and build up a bash
# hash of device paths based on uuid. Clear all disks in the model
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*DEFEC8EDCAFE)
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*DEFEC8EDCAFE)
fi
disk_list["disk1"]=\$disk_list_item

if [[ ! -b \${disk_list["disk1"]} ]]; then
echo "ERROR: Could not find disk of UUID 'DEFEC8EDCAFE'" >> /dev/tty1;
read;
exit 1;
fi
drive_dev=\$(basename \$(find /dev/disk/by-id -iname scsi\*DEFEC8EDCAFE -printf "%l"))
if [ ! -n "$drive_dev" ]; then
drive_dev=\$(basename \$(find /dev/disk/by-id -iname cciss\*DEFEC8EDCAFE -printf "%l"))
fi
clearpart_devs=\${clearpart_devs},\${drive_dev}
echo "clearpart --initlabel --all --drives=\${clearpart_devs/#,/}">/tmp/partitioninfo
# Second loop to generate the partition tables - NB. must be after the clearpart command - hence 2 loops
echo "part /boot --fstype=ext4 --size=500 --ondisk=${disk_list["disk1"]}" >>/tmp/partitioninfo
# Create PV(s) for Root VG
echo "part pv.01vg_root --size=511500 --ondisk=${disk_list["disk1"]}" >> /tmp/partitioninfo
# Create Root VG
echo "volgroup vg_root --pesize=4096 pv.01vg_root" >> /tmp/partitioninfo
# Create Root VG Logical Volumes
echo "logvol / --fstype=ext4 --name=rvg_root --vgname=vg_root --size=40960" >> /tmp/partitioninfo
'''.strip()

        node1 = nodes[0]
        self.mock_callback_api.query.return_value = [node1]
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._generate_lvm_kickstart(tasks, node1, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assertEquals(expected_snippet, snippet)

        expected_snippet = r'''
# Hash map
declare -A disk_list
# Loop through the data structure we have been passed in and build up a bash
# hash of device paths based on uuid. Clear all disks in the model
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*defec8edcafe)
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*defec8edcafe)
fi
disk_list["disk2"]=\$disk_list_item

if [[ ! -b \${disk_list["disk2"]} ]]; then
echo "ERROR: Could not find disk of UUID 'defec8edcafe'" >> /dev/tty1;
read;
exit 1;
fi
drive_dev=\$(basename \$(find /dev/disk/by-id -iname scsi\*defec8edcafe -printf "%l"))
if [ ! -n "$drive_dev" ]; then
drive_dev=\$(basename \$(find /dev/disk/by-id -iname cciss\*defec8edcafe -printf "%l"))
fi
clearpart_devs=\${clearpart_devs},\${drive_dev}
echo "clearpart --initlabel --all --drives=\${clearpart_devs/#,/}">/tmp/partitioninfo
# Second loop to generate the partition tables - NB. must be after the clearpart command - hence 2 loops
echo "part /boot --fstype=ext4 --size=500 --ondisk=${disk_list["disk2"]}" >>/tmp/partitioninfo
# Create PV(s) for Root VG
echo "part pv.01vg_root --size=19980 --ondisk=${disk_list["disk2"]}" >> /tmp/partitioninfo
# Create Root VG
echo "volgroup vg_root --pesize=4096 pv.01vg_root" >> /tmp/partitioninfo
# Create Root VG Logical Volumes
echo "logvol / --fstype=ext4 --name=rvg_root --vgname=vg_root --size=40960" >> /tmp/partitioninfo
'''.strip()

        tasks = []
        node2 = nodes[1]
        self.mock_callback_api.query.return_value = [node2]
        self.testClass._generate_lvm_kickstart(tasks, node2, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assertEquals(expected_snippet, snippet)

        expected_snippet = r'''
# Hash map
declare -A disk_list
# Loop through the data structure we have been passed in and build up a bash
# hash of device paths based on uuid. Clear all disks in the model
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*DeFec8EFCafE)
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*DeFec8EFCafE)
fi
disk_list["disk3"]=\$disk_list_item

if [[ ! -b \${disk_list["disk3"]} ]]; then
echo "ERROR: Could not find disk of UUID 'DeFec8EFCafE'" >> /dev/tty1;
read;
exit 1;
fi
drive_dev=\$(basename \$(find /dev/disk/by-id -iname scsi\*DeFec8EFCafE -printf "%l"))
if [ ! -n "$drive_dev" ]; then
drive_dev=\$(basename \$(find /dev/disk/by-id -iname cciss\*DeFec8EFCafE -printf "%l"))
fi
clearpart_devs=\${clearpart_devs},\${drive_dev}
echo "clearpart --initlabel --all --drives=\${clearpart_devs/#,/}">/tmp/partitioninfo
# Second loop to generate the partition tables - NB. must be after the clearpart command - hence 2 loops
echo "part /boot --fstype=ext4 --size=500 --ondisk=${disk_list["disk3"]}" >>/tmp/partitioninfo
# Create PV(s) for Root VG
echo "part pv.01vg_root --size=4193804 --ondisk=${disk_list["disk3"]}" >> /tmp/partitioninfo
# Create Root VG
echo "volgroup vg_root --pesize=4096 pv.01vg_root" >> /tmp/partitioninfo
# Create Root VG Logical Volumes
echo "logvol / --fstype=ext4 --name=rvg_root --vgname=vg_root --size=40960" >> /tmp/partitioninfo
'''.strip()

        tasks = []
        node3 = nodes[2]
        self.mock_callback_api.query.return_value = [node3]
        self.testClass._generate_lvm_kickstart(tasks, node3, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assertEquals(expected_snippet, snippet)

    def _setup_mock_nodes2(self, os_version='rhel7', boot_mode='bios'):
        service = Mock(get_vpath=lambda: '/ms/cobbler_service')
        service.boot_mode = boot_mode

        disk1 = Mock()
        disk1.uuid = 'DeFec8EFCafE'
        disk1.item_type = Mock()
        disk1.item_type.structure = {'uuid': Mock()}
        disk1.item_type.structure['uuid'].updatable_plugin = True
        disk1.size = '4T'
        disk1.name = 'hd0'
        disk1.bootable = 'true'
        disk1.item_id = 'disk1'
        disk2 = Mock()
        disk2.uuid = '123456EFCAFE'
        disk2.size = '2T'
        disk2.name = 'secondary'
        disk2.item_id = 'disk2'
        disk2.bootable = 'false'
        disk2.shared = 'false'
        disk3 = Mock()
        disk3.uuid = '123f2ec1a9f3'
        disk3.size = '2T'
        disk3.name = 'tertiary'
        disk3.item_id = 'disk3'
        disk4 = Mock()
        disk4.uuid = '123f2ec1a9f4'
        disk4.size = '2T'
        disk4.name = 'fourth'
        disk4.item_id = 'disk4'

        storage_profile = Mock()
        vg_root = Mock(volume_group_name='vg_root', item_id='vg1')
        vg_root.physical_devices = [Mock(device_name='hd0'),
                                    Mock(device_name='fourth')]
        vg_root.file_systems = [Mock(mount_point='/', type='ext4', size='40G',
                                     item_id='root',
                                     get_vpath=lambda: '/foo/hda')]
        vg_data = Mock(volume_group_name='vg_data', item_id='vg2')
        vg_data.physical_devices = [Mock(device_name='secondary')]
        vg_data.file_systems = [Mock(mount_point='/data', type='ext4',
                                     size='20G',
                                     item_id='data',
                                     get_vpath=lambda: '/foo/xyz')]

        storage_profile.volume_groups = [vg_root, vg_data]
        storage_profile.view_root_vg = 'vg_root'

        sys1 = Mock()
        sys1.boot_mode = boot_mode

        node1 = Mock()
        node1.hostname = 'node3'
        node1.system = sys1
        node1.system.disks = [disk1, disk2, disk3, disk4]
        self.all_disk_uuids = [disk1.uuid, disk2.uuid, disk3.uuid, disk4.uuid]
        node1.storage_profile = storage_profile
        node1.os.version = os_version

        nodes = [node1]
        return nodes, service, self.all_disk_uuids

    def _setup_mock_nodes2_with_shared_disk(self):
        nodes, service, self.all_disk_uuids = self._setup_mock_nodes2()

        shared_disk = Mock()
        shared_disk.uuid = 'shared_disk_uuid'
        shared_disk.size = '2T'
        shared_disk.name = 'shared'
        shared_disk.item_id = 'shared_disk'
        shared_disk.bootable = 'false'
        shared_disk.shared = 'true'

        nodes[0].system.disks.insert(0, shared_disk)
        self.all_disk_uuids = self.all_disk_uuids.extend(shared_disk.uuid)

        return nodes, service, self.all_disk_uuids

    def test_clear_correct_partition(self):
        nodes, service, all_uuids = self._setup_mock_nodes2()
        node1_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node1.test_clear_correct_partition.snippet')
        expected_snippet_1 = open(node1_part_snippet).read().strip()

        tasks = []
        node = nodes[0]
        self.mock_callback_api.query.return_value = nodes
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._generate_lvm_kickstart(tasks, node, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)

        self.assert_snippet_by_line(expected_snippet_1, snippet)
        self.assertEquals(expected_snippet_1, snippet)

    def test_clear_correct_partition_uefi(self):
        nodes, service, all_uuids = self._setup_mock_nodes2(boot_mode='uefi')
        node1_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node1.test_clear_correct_partition_uefi.snippet')
        expected_snippet_1 = open(node1_part_snippet).read().strip()

        tasks = []
        node = nodes[0]
        self.mock_callback_api.query.return_value = nodes
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._generate_lvm_kickstart(tasks, node, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)

        self.assert_snippet_by_line(expected_snippet_1, snippet)
        self.assertEquals(expected_snippet_1, snippet)

    def test_clear_correct_partition_rhel6(self):
        nodes, service, all_uuids = self._setup_mock_nodes2(os_version='rhel6')

        expected_snippet = r'''

# Hash map
declare -A disk_list
# Loop through the data structure we have been passed in and build up a bash
# hash of device paths based on uuid. Clear all disks in the model
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*DeFec8EFCafE)
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*DeFec8EFCafE)
fi
disk_list["disk1"]=\$disk_list_item

if [[ ! -b \${disk_list["disk1"]} ]]; then
echo "ERROR: Could not find disk of UUID 'DeFec8EFCafE'" >> /dev/tty1;
read;
exit 1;
fi
drive_dev=\$(basename \$(find /dev/disk/by-id -iname scsi\*DeFec8EFCafE -printf "%l"))
if [ ! -n "$drive_dev" ]; then
drive_dev=\$(basename \$(find /dev/disk/by-id -iname cciss\*DeFec8EFCafE -printf "%l"))
fi
clearpart_devs=\${clearpart_devs},\${drive_dev}
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*123456EFCAFE)
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*123456EFCAFE)
fi
disk_list["disk2"]=\$disk_list_item

if [[ ! -b \${disk_list["disk2"]} ]]; then
echo "ERROR: Could not find disk of UUID '123456EFCAFE'" >> /dev/tty1;
read;
exit 1;
fi
drive_dev=\$(basename \$(find /dev/disk/by-id -iname scsi\*123456EFCAFE -printf "%l"))
if [ ! -n "$drive_dev" ]; then
drive_dev=\$(basename \$(find /dev/disk/by-id -iname cciss\*123456EFCAFE -printf "%l"))
fi
clearpart_devs=\${clearpart_devs},\${drive_dev}
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*123f2ec1a9f3)
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*123f2ec1a9f3)
fi
disk_list["disk3"]=\$disk_list_item

if [[ ! -b \${disk_list["disk3"]} ]]; then
echo "ERROR: Could not find disk of UUID '123f2ec1a9f3'" >> /dev/tty1;
read;
exit 1;
fi
drive_dev=\$(basename \$(find /dev/disk/by-id -iname scsi\*123f2ec1a9f3 -printf "%l"))
if [ ! -n "$drive_dev" ]; then
drive_dev=\$(basename \$(find /dev/disk/by-id -iname cciss\*123f2ec1a9f3 -printf "%l"))
fi
clearpart_devs=\${clearpart_devs},\${drive_dev}
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*123f2ec1a9f4)
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*123f2ec1a9f4)
fi
disk_list["disk4"]=\$disk_list_item

if [[ ! -b \${disk_list["disk4"]} ]]; then
echo "ERROR: Could not find disk of UUID '123f2ec1a9f4'" >> /dev/tty1;
read;
exit 1;
fi
drive_dev=\$(basename \$(find /dev/disk/by-id -iname scsi\*123f2ec1a9f4 -printf "%l"))
if [ ! -n "$drive_dev" ]; then
drive_dev=\$(basename \$(find /dev/disk/by-id -iname cciss\*123f2ec1a9f4 -printf "%l"))
fi
clearpart_devs=\${clearpart_devs},\${drive_dev}
echo "clearpart --initlabel --all --drives=\${clearpart_devs/#,/}">/tmp/partitioninfo
# Second loop to generate the partition tables - NB. must be after the clearpart command - hence 2 loops
echo "part /boot --fstype=ext4 --size=500 --ondisk=${disk_list["disk1"]}" >>/tmp/partitioninfo
# Create PV(s) for Root VG
echo "part pv.01vg_root --size=4193804 --ondisk=${disk_list["disk1"]}" >> /tmp/partitioninfo
echo "part pv.02vg_root --size=2097152 --ondisk=${disk_list["disk4"]}" >> /tmp/partitioninfo
# Create Root VG
echo "volgroup vg_root --pesize=4096 pv.01vg_root pv.02vg_root" >> /tmp/partitioninfo
# Create Root VG Logical Volumes
echo "logvol / --fstype=ext4 --name=vg1_root --vgname=vg_root --size=40960" >> /tmp/partitioninfo
'''.strip()

        tasks = []
        node = nodes[0]
        self.mock_callback_api.query.return_value = nodes
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._generate_lvm_kickstart(tasks, node, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assertEquals(expected_snippet, snippet)

    def test_generate_cobbler_records(self):
        tasks = []
        services = self.api.query("cobbler-service")
        service = services[0]
        self.testClass._generate_cobbler_configure(service, self.api, tasks,
                                                   False)
        self.testClass._generate_cobbler_records(service, self.api, tasks)
        add_profile_task = [task for task in tasks \
                            if task.call_type == "cobblerdata::add_profile"][0]
        add_system_tasks = [task for task in tasks \
                            if task.call_type == "cobblerdata::add_system"]
        self.assertTrue(add_profile_task.kwargs['distro'] == \
                        add_profile_task.call_id)

    def test_convert_to_mb(self):
        self.assertEqual(20, self.testClass._convert_to_mb("20M"))
        self.assertEqual(20480, self.testClass._convert_to_mb("20G"))
        self.assertEqual(20971520, self.testClass._convert_to_mb("20T"))

    def test_convert_to_mb_nasty_input(self):
        ''' The disk size in the disk item type is validated with a regex to
        make sure it has the proper values, so this test might be useless '''
        self.assertEqual(None, self.testClass._convert_to_mb("9001J"))

    def test_get_timezone(self):
        read_data = \
            ['Local time: Fri 2020-07-03 17:09:40 IST',
             'Universal time: Fri 2020-07-03 16:09:40 UTC',
             'RTC time: Fri 2020-07-03 16:09:40'
             'NTP enabled: yes',
             'NTP synchronized: yes',
             'RTC in local TZ: no',
             'Time zone: Europe/Gijon (IST, +0100)',
             'DST active: yes',
             'Last DST change: DST began at',
             'Sun 2020-03-29 00:59:59 GMT',
             'Sun 2020-03-29 02:00:00 IST',
             'Next DST change: DST ends (the clock jumps one hour backwards) at',
             'Sun 2020-10-25 01:59:59 IST',
             'Sun 2020-10-25 01:00:00 GMT']
        with patch('__builtin__.open') as mock_open:
            mock = MagicMock(spec=file)
            mock.__enter__.return_value.readlines.return_value = read_data
            mock_open.return_value = mock
            self.assertEqual("--utc Europe/Gijon",
                             self.testClass._get_timezone())

    def test_get_timezone_no_tz_in_output(self):

        read_data = \
            ['Local time: Fri 2020-07-03 17:09:40 IST',
             'Universal time: Fri 2020-07-03 16:09:40 UTC',
             'RTC time: Fri 2020-07-03 16:09:40'
             'NTP enabled: yes',
             'NTP synchronized: yes',
             'RTC in local TZ: no',
             'DST active: yes',
             'Last DST change: DST began at',
             'Sun 2020-03-29 00:59:59 GMT',
             'Sun 2020-03-29 02:00:00 IST',
             'Next DST change: DST ends (the clock jumps one hour backwards) at',
             'Sun 2020-10-25 01:59:59 IST',
             'Sun 2020-10-25 01:00:00 GMT']
        with patch('__builtin__.open') as mock_open:
            mock = MagicMock(spec=file)
            mock.__enter__.return_value.readlines.return_value = read_data
            mock_open.return_value = mock
            self.assertEqual("--utc Europe/Dublin",
                             self.testClass._get_timezone())

    @patch("__builtin__.open")
    def test_get_timezone_IOError(self, m_open):
        m_open.side_effect = IOError()
        self.assertEqual("--utc Europe/Dublin",
                         self.testClass._get_timezone())

    @patch("__builtin__.open")
    def test_get_timezone_IndexError(self, m_open):
        m_open.side_effect = IndexError()
        self.assertEqual("--utc Europe/Dublin",
                         self.testClass._get_timezone())

    def test_check_node(self):
        with patch('litp.core.rpc_commands._run_process') as mock_run_rpc:
            test_obj = bootmgr_plugin.BootManagerPlugin()
            mock_run_rpc.return_value = 1, 'useless'
            result = test_obj._check_node("random_hostname")
            self.assertTrue(result)
            mock_run_rpc.return_value = 4, 'useless'
            result = test_obj._check_node("random_hostname")
            self.assertFalse(result)

    def test_validate_cobbler_service_exists(self):
        res = self.testClass._validate_cobbler_service_exists(self.api)
        self.assertEqual([], res)
        # self.testClass._get_cobbler_service = lambda x: None
        self.api.query = lambda x: None
        res = self.testClass._validate_cobbler_service_exists(self.api)
        self.assertTrue(len(res) == 1)
        self.assertEqual(ValidationError, type(res[0]))

    def test_validate_br_in_libvirt(self):
        service = self.testClass._get_cobbler_service(self.api)
        # no libvirt in system, nothing to validate
        res = self.testClass._validate_br_in_libvirt(self.api, service)
        self.assertEqual([], res)

        # now with a 100% more of libvirt
        items = {}

        provider_path = "/infrastructure/system_providers/libvirt-provider"
        items[provider_path] = self.model.create_item(
            "libvirt-provider", provider_path, name='libvirt1'
        )

        path = "/infrastructure/system_providers/libvirt-provider/systems/vm3"
        items[path] = self.model.create_item(
            "libvirt-system", path, system_name="vm3"
        )

        system_path = "/infrastructure/systems/libvirt1"
        items[system_path] = self.model.create_item(
            "libvirt-system", system_path, system_name='noprovider'
        )

        path = "/ms/libvirt"
        items[path] = self.model.create_inherited(provider_path, path)

        path = '/deployments/d1/clusters/c1/nodes/n3'
        items[path] = self.model.create_item(
            "node", path, hostname='n3'
        )

        path = '/deployments/d1/clusters/c1/nodes/n3/system'
        items[path] = self.model.create_inherited(system_path, path)

        self.model.update_item(system_path, system_name='vm3')

        for path, item in items.iteritems():
            self.assertTrue(
                isinstance(item, ModelItem),
                "BootManagerPluginTest.test_validate_br_in_libvirt() failed "
                "create or inherit '%s', got '%s' instead of "
                "ModelItem" % (path, item)
            )
        res = self.testClass._validate_br_in_libvirt(self.api, service)
        self.assertEqual([], res)

    def test_validate_no_errors_with_good_deployment(self):
        self.assertEqual([], self.testClass.validate_model(self.api))

    def test_validate_no_errors_with_good_deployment2(self):
        os_profile = self.model.get_item("/software/profiles/rhel_6_2")
        self.assertTrue(isinstance(os_profile, ModelItem))
        os_profile.set_updated()
        self.model.update_item("/software/profiles/rhel_6_2", path='/tmp')
        self.assertEqual([], self.testClass.validate_model(self.api))

    def test_validate_error_if_no_cobbler(self):
        self.model.remove_item("/ms/services/cobbler")
        res = self.testClass.validate_model(self.api)
        self.assertTrue(1, len(res))
        self.assertTrue(ValidationError, type(res[0]))

    def test_validate_no_nodes_no_cobbler(self):
        self.testClass._nodes_in_the_deployment = Mock(return_value=[])
        self.testClass._get_new_node_systems = Mock(return_value=[])
        self.model.remove_item("/ms/services/cobbler")
        self.assertEqual([], self.testClass.validate_model(self.api))

    def test_convert_to_gigabytes(self):
        bm = bootmgr_plugin.BootManagerPlugin()
        self.assertEqual("1", bm.convert_to_gigabytes("500M"))
        self.assertEqual("31", bm.convert_to_gigabytes("28672M"))
        self.assertEqual("31", bm.convert_to_gigabytes("28G"))
        self.assertEqual("108", bm.convert_to_gigabytes("100G"))
        self.assertEqual("1074", bm.convert_to_gigabytes("1000G"))
        self.assertEqual("1074", bm.convert_to_gigabytes("1T"))
        self.assertEqual("10738", bm.convert_to_gigabytes("10T"))

        self.assertEqual("5", bm.convert_to_gigabytes(""))
        self.assertEqual("5", bm.convert_to_gigabytes("5"))
        self.assertEqual("5", bm.convert_to_gigabytes("G"))

    def test_wait_for_callback(self):
        bm = bootmgr_plugin.BootManagerPlugin()

        mock_api = MagicMock()
        test_callback = MagicMock(return_value=True)
        mock_api.is_running.return_value = False
        bm._wait_for_callback(mock_api, "test_message", test_callback)

        test_callback = MagicMock(return_value=False)
        mock_api.is_running.return_value = False
        self.assertRaises(
            PlanStoppedException,
            bm._wait_for_callback,
            mock_api,
            "test_message",
            test_callback)

        bm._get_current_time = MagicMock()
        bm._get_current_time.side_effect = [0.0, 36.0, 360.0, 3600.0]
        old_time_sleep = time.sleep
        time.sleep = MagicMock()
        mock_api.is_running.return_value = True
        self.assertRaises(
            CallbackExecutionException,
            bm._wait_for_callback,
            mock_api,
            "test_message",
            test_callback
        )
        time.sleep = old_time_sleep

    def test_network_dict(self):

        class NetworkItem(MagicMock):
            def __init__(self, item_id, subnet):
                super(NetworkItem, self).__init__()
                self.item_id = item_id
                self.subnet = subnet

        network_item = NetworkItem(
            "mgmt",
            "192.168.16.0/23"
        )
        network_item_2 = NetworkItem(
            "mgmt",
            "192.168.17.0/23"
        )
        network_item_3 = NetworkItem(
            "mgmt",
            None
        )

        network_dict = self.testClass._network_dict(network_item)
        network_dict_2 = self.testClass._network_dict(network_item_2)
        network_dict_3 = self.testClass._network_dict(network_item_3)

        self.assertEqual(
            network_dict,
            {
                "subnet": "192.168.16.0",
                "netmask": "255.255.254.0"
            }
        )

        self.assertEqual(
            network_dict_2,
            {
                "subnet": "192.168.16.0",
                "netmask": "255.255.254.0"
            }
        )

        self.assertEqual(
            network_dict_3,
            None
        )

    def _mock_device(self, name, macaddress=None, master=None, bridge=None):
        if "." in name:
            dev_type = "vlan"
        else:
            if 'br' in name:
                dev_type = "bridge"
            else:
                dev_type = self.interface_name_regex.match(name).groups()[0]
        mock = Mock(
            device_name=name,
            item_type_id=dev_type,
            macaddress=macaddress,
            master=master,
            bridge=bridge,
            is_removed=lambda: False,
            is_for_removal=lambda: False
        )
        return mock

    def test_find_mac(self):
        """ This method tests the results of "_find_mac" method of
        BootManagerPlugin checking the macaddress retrieved comparing with the
        interfaces dict definition respecting the following rules:
         1. eth interfaces always have macaddress;
         2. bond, vlans and bridges doesn't have macaddress attribute;
         3. the macaddress of a bond is considered as the macaddress of the
         first of its eth slaves sorted alphabetically by the device name.
         E.g.: (eth1, eth0) -> bond0, so the macaddress of bond0 is the
         macaddress of eth0.
         4. the macaddress of a vlan is the macaddress of the interface
         associated: e.g.: if vlan is eth1.132 the macaddress is the macaddress
         of eth1.
         5. the macaddress of a bridge is the based on what device is bridged
            that is if a vlan is bridged then find the mac of the vlan
            if a bond is bridged find the mac of the bond
         6. if the interface associated to a vlan is bond the macaddress will
         be considered as explained the rule number 3.
        """
        bm = bootmgr_plugin.BootManagerPlugin()
        nodes, service, all_uuids = self._setup_mock_nodes()
        interfaces = dict([
            ('eth5', ('ee:ee:ee:ee:ee:ee', None, 'br0')),
            ('eth6', ('ff:ff:ff:ff:ff:ff', None, 'br1')),
            ('eth0', ('08:00:27:5B:C1:3A', 'bond0', None)),
            ('eth1', ('aa:bb:cc:dd:ee:f1', 'bond0', None)),
            ('eth2', ('bb:bb:bb:bb:bb:bb', 'bond1', None)),
            ('eth3', ('cc:cc:cc:cc:cc:cc', None, None)),
            ('eth4', ('dd:dd:dd:dd:dd:dd', 'bond1', None)),
            ('eth5', ('ee:ee:ee:ee:ee:ee', 'None', 'br0')),
            ('eth6', ('ff:ff:ff:ff:ff:ff', 'None', 'br1')),
            ('eth0.123', (None, None, None)),  # vlan interface
            ('bond0.666', (None, None, None)),
            # vlan interface associated to a bond
            ('bond1.111', (None, None, None)),
            # vlan interface associated to a bond
            ('br0', (None, None, None)),
            ('br1', (None, None, None)),
            ('bond0', (None, None, None)),
            ('bond1', (None, None, None))
        ])
        dev = lambda i: self._mock_device(i[0], *i[1])

        # building the bonds dict
        bonds = {}
        for dev_name, mac_master in interfaces.items():
            macaddress, master, bridge = mac_master
            if not master:
                continue
            if master.startswith('br'):
                continue
            if not bonds.has_key(master):
                bonds[master] = []
            bonds[master].append((dev_name, macaddress))

        bridges = {}
        for dev_name, dev_bridge in interfaces.items():
            macaddress, master, bridge = dev_bridge
            if not bridge:
                continue
            if bridge.startswith('br'):
                if not bridges.has_key(bridge):
                    bridges[bridge] = []
                print "append macaddress now"
                bridges[bridge].append((dev_name, macaddress))

        def _mock_query(name):
            return [dev(i) for i in interfaces.items()
                    if
                    self.interface_name_regex.match(i[0]).groups()[0] == name]

        for node in nodes:
            node.network_interfaces = [dev(i) for i in interfaces.items()]
            node.query = _mock_query
            for dev_name, mac_master in interfaces.items():
                original_dev = dev_name
                macaddress, master, bridge = mac_master
                retrieved_mac = bm._find_mac(node, dev_name)
                if '.' in dev_name:
                    dev_name = dev_name.split('.')[0]
                    macaddress = interfaces[dev_name][0]
                if dev_name in bonds:
                    slaves = bonds[dev_name]
                    slaves.sort()
                    macaddress = slaves[0][1]
                if dev_name in bridges:
                    brgs = bridges[dev_name]
                    brgs.sort()
                    macaddress = brgs[0][1]
                msg = "The retrieved macaddress %s of %s interface is not " \
                      "expected: %s." % (
                      retrieved_mac, original_dev, macaddress)
                self.assertEquals(retrieved_mac, macaddress, msg)

    def _setup_UUIDless_mock_nodes(self, os_version='rhel6'):
        service = Mock(get_vpath=lambda: '/ms/cobbler_service')

        disk1 = BootMgrMockDisk('disk1', 'hd0', '4T', 'kgb', 'true')
        disk1.item_type.structure = {'uuid': Mock()}
        disk1.item_type.structure['uuid'].updatable_plugin = False
        self.all_disk_uuids = [disk1.uuid]

        storage_profile = BootMgrMockStorageProfile("sp1", "lvm")
        vg_root = Mock(volume_group_name='vg_root', item_id='vg1')
        vg_root.physical_devices = [Mock(device_name='hd0')]
        vg_root.file_systems = [Mock(mount_point='/', type='ext4', size='40G',
                                     item_id='root',
                                     get_vpath=lambda: '/foo/hda')]
        vg_data = Mock(volume_group_name='vg_data', item_id='vg2')
        vg_data.physical_devices = [Mock(device_name='secondary')]
        vg_data.file_systems = [Mock(mount_point='/data', type='ext4',
                                     size='20G',
                                     item_id='data',
                                     get_vpath=lambda: '/foo/xyz')]

        storage_profile.volume_groups = [vg_root, vg_data]
        storage_profile.view_root_vg = 'vg_root'

        node1 = BootMgrMockNode('node1', 'node1')
        node1.system.disks = [disk1]
        node1.storage_profile = storage_profile
        node1.os.version = os_version

        nodes = [node1]
        return nodes, service, self.all_disk_uuids

    def test_kgb_bootloader_fragment(self):
        nodes, service, all_uuids = self._setup_UUIDless_mock_nodes()
        tasks = []
        mock_ms = Mock(get_vpath=lambda: '/ms', hostname='ms1')
        node1 = nodes[0]
        cluster = Mock()
        cluster.parent = [cluster]
        node1.get_cluster = Mock(return_value=cluster)
        updated_nodes = [node1]
        self.mock_callback_api.query.return_value = updated_nodes
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._generate_bootloader_fragments(self.mock_callback_api,
                                                      mock_ms, tasks,
                                                      updated_nodes, service)
        self.assertEquals(1, len(tasks))
        self.assertEquals('cobbler::bootloader_name', tasks[0].call_type)

    def test_kgb_bootloader_clearpart(self):
        nodes, service, all_uuids = self._setup_UUIDless_mock_nodes('rhel7')
        node1_part_snippet = os.path.join(self.partition_snippets_dir,
                                          'node1.test_kgb_bootloader_clearpart.snippet')
        expected_snippet_1 = open(node1_part_snippet).read().strip()
        tasks = []
        node = nodes[0]
        self.mock_callback_api.query.return_value = nodes
        self.testClass._get_all_disk_uuids = MagicMock(return_value=all_uuids)
        self.testClass._generate_lvm_kickstart(tasks, node, service)
        snippet = self._extract_partition_snippet_from_tasks(tasks)
        self.assert_snippet_by_line(expected_snippet_1, snippet)
        self.assertEquals(expected_snippet_1, snippet)

    def test_uuid_bootloader_fragment(self):
        nodes, service, all_uuids = self._setup_mock_nodes2()
        tasks = []
        mock_ms = Mock(get_vpath=lambda: '/ms', hostname='ms1')
        node1 = nodes[0]
        cluster = Mock()
        cluster.parent = [cluster]
        node1.get_cluster = Mock(return_value=cluster)
        updated_nodes = [node1]
        self.mock_callback_api.query.return_value = updated_nodes
        self.testClass._generate_bootloader_fragments(self.mock_callback_api,
                                                      mock_ms, tasks,
                                                      updated_nodes, service)
        self.assertEquals(1, len(tasks))
        self.assertEquals('cobbler::bootloader', tasks[0].call_type)

    @patch('bootmgr_plugin.bootmgr_plugin.BootManagerPlugin._is_os_reinstall')
    @patch('bootmgr_plugin.bootmgr_plugin._log')
    def test_uuid_bootloader_fragment_shared_disks(self, patch_log,
                                                   patch_is_os_reinstall):
        nodes, service, all_uuids = self._setup_mock_nodes2_with_shared_disk()
        tasks = []
        mock_ms = Mock(get_vpath=lambda: '/ms', hostname='ms1')
        node1 = nodes[0]
        cluster_item_type = Mock(item_type_id='vcs-cluster')
        fen_disk1 = Mock(uuid="123")
        fen_disk2 = Mock(uuid="456")
        fen_disk3 = Mock(uuid="789")
        cluster = Mock(fencing_disks=[fen_disk1, fen_disk2, fen_disk3],
                       item_type=cluster_item_type)
        cluster.parent = [cluster]
        node1.get_cluster = Mock(return_value=cluster)
        updated_nodes = [node1]
        patch_is_os_reinstall.return_value = False
        self.mock_callback_api.query.return_value = updated_nodes
        self.testClass._generate_bootloader_fragments(self.mock_callback_api,
                                                      mock_ms, tasks,
                                                      updated_nodes, service)
        self.assertEqual(1, len(tasks))
        self.assertEqual('cobbler::bootloader', tasks[0].call_type)
        self.assertEqual(['123', '456', '789'], tasks[0].kwargs['shared_uuids'])
        self.assertEqual(patch_log.trace.debug.call_args_list, [
            call("_generate_bootloader_fragments.  Nodes: " + str(nodes)),
            call('Boot disk for node node3 is identified by uuid 123f2ec1a9f4'),
            call(
                'Passing shared_disks argument: "[\'123\', \'456\', \'789\']" to ConfigTask')]
                         )
        patch_is_os_reinstall.return_value = True
        tasks = []
        patch_log.trace.debug.call_args_list = []
        self.mock_callback_api.query.return_value = updated_nodes
        self.testClass._generate_bootloader_fragments(self.mock_callback_api,
                                                      mock_ms, tasks,
                                                      updated_nodes, service)

        self.assertEqual(['shared_disk_uuid', '123', '456', '789'],
                         tasks[0].kwargs['shared_uuids'])
        self.assertEqual(patch_log.trace.debug.call_args_list, [
            call("_generate_bootloader_fragments.  Nodes: " + str(nodes)),
            call('Boot disk for node node3 is identified by uuid 123f2ec1a9f4'),
            call(
                'Passing shared_disks argument: "[\'shared_disk_uuid\', \'123\', \'456\', \'789\']" to ConfigTask')]
                         )

    def test_do_add_system_callback(self):
        _cobbler_mco_mock = Mock()
        bmp = bootmgr_plugin.BootManagerPlugin()
        bmp._do_cobbler_mco = _cobbler_mco_mock
        cb_api = type('MockCB', (object,), {'is_running': lambda s: True})()
        nodes = ['ms1']
        system_name = 'node1'
        all_args = {'profile': 'profile1', 'interfaces':
            {'eth0': {'dns_name': u'node1',
                      'ip_address': u'10.10.10.102',
                      'mac_address': u'08:00:27:65:C8:B4'}
             },
                    'hostname': 'node1', 'kickstart': 'file1.ks'}
        bmp._add_system_callback(cb_api, nodes, system_name, **all_args)
        call_list = bmp._do_cobbler_mco.call_args_list
        # skips first element, it's the cb_api above
        self.assertEquals(call_list[0][0][1:3], (['ms1'], 'remove_system'))
        self.assertEquals(call_list[1][0][1:3], (['ms1'], 'add_system'))
        self.assertEquals(call_list[2][0][1:3], (['ms1'], 'edit_system'))
        self.assertEquals(call_list[3][0][1:3], (['ms1'], 'sync'))
        # first call: add
        call_list_add = call_list[1]
        self.assertTrue('profile' in call_list_add[0][3])
        self.assertTrue('system' in call_list_add[0][3])
        self.assertEquals(len(call_list_add[0][3]), 2)
        # second call: edit
        call_list_edit = call_list[2]
        self.assertTrue('profile' in call_list_edit[0][3])
        self.assertTrue('system' in call_list_edit[0][3])
        self.assertTrue('interface' in call_list_edit[0][3])
        self.assertEquals(call_list_edit[0][3]['interface'], 'eth0')

    def test_do_add_system_multiple_ifaces(self):
        _cobbler_mco_mock = Mock()
        bmp = bootmgr_plugin.BootManagerPlugin()
        bmp._do_cobbler_mco = _cobbler_mco_mock
        cb_api = type('MockCB', (object,), {'is_running': lambda s: True})()
        nodes = ['ms1']
        system_name = 'node1'
        all_args = {'profile': 'profile1', 'interfaces':
            {'eth0': {'dns_name': u'node1',
                      'ip_address': u'10.10.10.102',
                      'mac_address': u'08:00:27:65:C8:B4'},
             'eth1': {'dns_name': u'node1-iface2',
                      'ip_address': u'10.10.20.2',
                      'mac_address': u'08:00:27:11:22:33'}
             },
                    'hostname': 'node1', 'kickstart': 'file1.ks'}
        bmp._add_system_callback(cb_api, nodes, system_name, **all_args)
        call_list = bmp._do_cobbler_mco.call_args_list
        # skips first element, it's the cb_api above
        self.assertEquals(call_list[0][0][1:3], (['ms1'], 'remove_system'))
        self.assertEquals(call_list[1][0][1:3], (['ms1'], 'add_system'))
        self.assertEquals(call_list[2][0][1:3], (['ms1'], 'edit_system'))
        self.assertEquals(call_list[3][0][1:3], (['ms1'], 'edit_system'))
        self.assertEquals(call_list[4][0][1:3], (['ms1'], 'sync'))
        # first call: add
        call_list_add = call_list[1]
        self.assertTrue('profile' in call_list_add[0][3])
        self.assertTrue('system' in call_list_add[0][3])
        self.assertEquals(len(call_list_add[0][3]), 2)
        # second/third call: edit
        call_list_edit_all = call_list[2:4]
        call_list_edit_all.sort(key=lambda k: k[0][3]['interface'])
        call_list_edit = call_list_edit_all[0]
        self.assertTrue('interface' in call_list_edit[0][3])
        self.assertEquals(call_list_edit[0][3]['interface'], 'eth0')
        self.assertEquals(call_list_edit[0][3]['ip_address'], '10.10.10.102')

        call_list_edit = call_list_edit_all[1]
        self.assertTrue('interface' in call_list_edit[0][3])
        self.assertEquals(call_list_edit[0][3]['interface'], 'eth1')
        self.assertEquals(call_list_edit[0][3]['ip_address'], '10.10.20.2')

    def test__validate_no_disk_base_items(self):

        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        disk = BootMgrMockDisk(item_id="d1",
                               name="hd0",
                               uuid="uuid",
                               size="10G",
                               bootable=True,
                               item_type_id="disk-base")
        sys = BootMgrMockSystem(item_id="s1")
        sys.disks.append(disk)
        node.system = sys
        errors = bootmgr_plugin.BootManagerPlugin()._validate_no_disk_base_items(
            [node])
        msg = 'Node mn1 has a disk "d1" of type "disk-base"'
        expected = ValidationError(item_path=disk.get_vpath(),
                                   error_message=msg)
        self.assertTrue(expected in errors)

    def test__remove_from_cobbler(self):
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        self.plugin._do_cobbler_remove_system = lambda *x: True
        self.plugin._do_cobbler_mco = lambda *x: True
        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        context = BootMgrMockContext()
        self.assertEqual(None, self.plugin._remove_from_cobbler(context,
                                                                [node], "ms"))

    # def test_get_boot_disk_uuid(self):
    #     sys = BootMgrMockSystem(item_id="s1")
    #     node = BootMgrMockNode(item_id="n1",
    #                            hostname="mn1")
    #     disk1 = BootMgrMockDisk('disk1', 'hd0', '500G', 'DEFEC8EDCAFE1',
    #                             'true')
    #     disk1.item_type.structure = {'uuid': 'DEFEC8EDCAFE1'}
    #     disk2 = BootMgrMockDisk('disk2', 'hd0', '20480M', 'DEFEC8EDCAFE2',
    #                             'false')
    #     disk2.item_type.structure = {'uuid': 'DEFEC8EDCAFE2'}
    #     os = BootMgrMockOs(item_id="os1",
    #                        version='rhel7')
    #     sys.disks = [disk1, disk2]
    #     node.system = sys
    #     node.os = os
    #     self.plugin = bootmgr_plugin.BootManagerPlugin()
    #     self.assertEqual('DEFEC8EDCAFE1', self.plugin._get_boot_disk_uuid(node))
    #     disk1.item_type_id = 'lun-disk'
    #     self.assertEqual('DEFEC8EDCAFE1', self.plugin._get_boot_disk_uuid(node))

    @patch('bootmgr_plugin.bootmgr_plugin.ConfigTask')
    def test__generate_cobbler_kickstart(self, MockConfigTask):
        ms = BootMgrMockMS()
        ms.query = MagicMock(return_value=[])
        sys = BootMgrMockSystem(item_id="s1")
        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        disk1 = BootMgrMockDisk('disk1', 'hd0', '500G', 'DEFEC8EDCAFE1',
                                'true')
        disk1.item_type.structure = {'uuid': 'DEFEC8EDCAFE1'}
        disk2 = BootMgrMockDisk('disk2', 'hd0', '20480M', 'DEFEC8EDCAFE2',
                                'false')
        disk2.item_type.structure = {'uuid': 'DEFEC8EDCAFE2'}
        os = BootMgrMockOs(item_id="os1",
                           version='rhel7')
        sys.disks = [disk1, disk2]
        node.system = sys
        node.os = os
        clus = BootMgrMockCluster(item_id="c1",
                                  cluster_type="my_clus_type")
        node.get_cluster = lambda: clus
        srv = MagicMock()
        srv.ksm_selinux_mode = "SE_Linux"
        srv.ksm_path = "path"
        srv.boot_mode = "bios"
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        self.plugin._get_timezone = lambda: "GMT"
        self.plugin._get_keyboard = lambda: "ie"
        description = 'Generate "%s" Cobbler kickstart file for node "%s"' % \
                      (node.os.version.upper(), node.hostname)
        tasks = []
        self.plugin._generate_cobbler_kickstart(ms, tasks, [node], srv)
        self.assertEqual(1, len(tasks))
        MockConfigTask.assert_called_once_with(
                        ms,
                        srv,
                        description,
                        'cobbler::kickstart',
                        node.hostname,
                        ksname='%s.ks' % (node.hostname,),
                        ms_hostname=ms.hostname,
                        selinux_mode=srv.ksm_selinux_mode,
                        cluster_type=clus.cluster_type,
                        partitioninfo='%include /tmp/partitioninfo',
                        keyboard=self.plugin._get_keyboard(),
                        timezone=self.plugin._get_timezone(),
                        path=srv.ksm_path,
                        os_version=node.os.version,
                        os_reinstall='false',
                        add_lvm_conf='false',
                        boot_mode=srv.boot_mode,
                        lvm_uuids=[],
                        openstack_env='false')

        # ----
        for (key, value, env_expected) in \
                       (('bogus1', 'bogus2', 'false'),
                        ('enm_deployment_type', 'bogus2', 'false'),
                        ('enm_deployment_type', 'vLITP_ENM_On_Rack_Servers', 'true')):

            MockConfigTask.reset_mock()
            mock_config_mngr = Mock(global_properties=[Mock(key=key,
                                                            value=value)])
            ms.query = MagicMock(return_value=[mock_config_mngr])
            tasks = []
            self.plugin._generate_cobbler_kickstart(ms, tasks, [node], srv)
            self.assertEqual(1, len(tasks))
            MockConfigTask.assert_called_once_with(
                            ms, srv, description,
                            'cobbler::kickstart',
                            node.hostname,
                            ksname='%s.ks' % (node.hostname,),
                            ms_hostname=ms.hostname,
                            selinux_mode=srv.ksm_selinux_mode,
                            cluster_type=clus.cluster_type,
                            partitioninfo='%include /tmp/partitioninfo',
                            keyboard=self.plugin._get_keyboard(),
                            timezone=self.plugin._get_timezone(),
                            path=srv.ksm_path,
                            os_version=node.os.version,
                            os_reinstall='false',
                            add_lvm_conf='false',
                            boot_mode=srv.boot_mode,
                            lvm_uuids=[],
                            openstack_env=env_expected)

    @patch('bootmgr_plugin.bootmgr_plugin.ConfigTask')
    def test__generate_cobbler_kickstart_rack(self, MockConfigTask):
        ms = BootMgrMockMS()
        ms.query = MagicMock(return_value=[])
        disk1 = BootMgrMockDisk('disk1', 'hd0', '500G', 'DEFEC8EDCAFE1',
                                'true')
        disk1.item_type.structure = {'uuid': 'DEFEC8EDCAFE1'}
        disk2 = BootMgrMockDisk('disk2', 'hd0', '20480M', 'DEFEC8EDCAFE2',
                                'false')
        disk2.item_type.structure = {'uuid': 'DEFEC8EDCAFE2'}
        sys = BootMgrMockSystem(item_id="s1")
        sys.disks = [disk1, disk2]
        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        os = BootMgrMockOs(item_id="os1",
                           version='rhel7')
        sp = BootMgrMockStorageProfile("sp1", "lvm")
        node.system = sys
        node.os = os
        node.storage_profile = sp
        vg_root = Mock(volume_group_name='vg_root', item_id='rvg')
        vg_root.physical_devices = [Mock(device_name='hd0')]
        vg_root.file_systems = [Mock(mount_point='/', type='ext4', size='40G',
                                     item_id='root',
                                     get_vpath=lambda: '/foo/hda')]
        vg_app = Mock(volume_group_name='vg_app', item_id='avg')
        vg_app.physical_devices = [Mock(device_name='hd1')]
        vg_app.file_systems = [Mock(mount_point='/', type='ext4', size='40G',
                                    item_id='app',
                                    get_vpath=lambda: '/foo/hda')]
        sp.volume_groups.extend([vg_root, vg_app])
        clus = BootMgrMockCluster(item_id="c1",
                                  cluster_type="sfha")
        node.get_cluster = lambda: clus
        srv = MagicMock()
        srv.ksm_selinux_mode = "SE_Linux"
        srv.ksm_path = "path"
        srv.boot_mode = "uefi"
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        self.plugin._get_timezone = lambda: "GMT"
        self.plugin._get_keyboard = lambda: "ie"
        tasks = []
        self.plugin._generate_cobbler_kickstart(ms, tasks, [node], srv)
        self.assertEqual(1, len(tasks))
        MockConfigTask.assert_called_once_with(
            ms,
            srv,
            'Generate "%s" Cobbler kickstart file for node "%s"' % (
                node.os.version.upper(), node.hostname),
            'cobbler::kickstart',
            node.hostname,
            ksname='%s.ks' % (node.hostname,),
            ms_hostname=ms.hostname,
            selinux_mode=srv.ksm_selinux_mode,
            cluster_type=clus.cluster_type,
            partitioninfo='%include /tmp/partitioninfo',
            keyboard=self.plugin._get_keyboard(),
            timezone=self.plugin._get_timezone(),
            path=srv.ksm_path,
            os_version=node.os.version,
            os_reinstall='false',
            boot_mode=srv.boot_mode,
            add_lvm_conf='false',
            lvm_uuids=['DEFEC8EDCAFE1', 'DEFEC8EDCAFE2'],
            openstack_env='false',
        )

    def test__get_kernel_options(self):
        node1 = Mock()
        node1.hostname = 'node1'
        node1.os.version = 'rhel7'
        kopts = self.testClass._get_kernel_options(node1.os.version)
        self.assertEqual(kopts['inst.repo'],
                         'http://@@http_server@@/7/os/x86_64/')

    def test__find_ip_for_node(self):
        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        node.network_interfaces = []
        network = MagicMock()
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        res = self.plugin._find_ip_for_node(node, network)
        self.assertEqual(res, None)

    def test__get_bridge(self):
        # test with empty array
        sys = BootMgrMockSystem(item_id="s1")
        sys.system_name = "my_system"
        providers = []
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        res = self.plugin._get_bridge(providers, sys)
        self.assertEqual(None, res)

        # test with providers
        prov = MagicMock()
        prov.bridge = "my_bridge"
        prov.systems = [sys]
        providers.append(prov)
        res = self.plugin._get_bridge(providers, sys)
        self.assertEqual("my_bridge", res)

    def test__get_bridge_macaddress(self):
        br = MagicMock()
        br.device_name = "my.bridge"
        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        res = self.plugin._get_bridge_macaddress(node, br)
        self.assertEqual(res, None)
        nic = MagicMock(spec=[u'bridge'])
        nic.item_type_id = "bond"
        nic.macaddress = "MY:MA:CA:AD:DR:ES:S"
        nic.bridge = "my.bridge"
        node.network_interfaces.append(nic)
        self.plugin._get_bond_macaddress = lambda *x: nic.macaddress
        res = self.plugin._get_bridge_macaddress(node, br)
        self.assertEqual(res, "MY:MA:CA:AD:DR:ES:S")

        nic.item_type_id = "vlan"
        nic.device_name = "my.bridge"

        iface = MagicMock()
        iface.item_type_id = "eth"
        iface.macaddress = "MY:MA:CA:AD:DR:ES:S"
        self.plugin._get_interface_by_name = lambda *x: iface
        res = self.plugin._get_bridge_macaddress(node, br)
        self.assertEqual(res, "MY:MA:CA:AD:DR:ES:S")

        iface.item_type_id = "bond"
        self.plugin._get_bond_macaddress = lambda *x: "MY:MA:CA:AD:DR:ES:S"
        res = self.plugin._get_bridge_macaddress(node, br)
        self.assertEqual(res, "MY:MA:CA:AD:DR:ES:S")

    def test__get_bond_eth_slaves(self):
        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        bond_interface = MagicMock("bond_interface")
        bond_interface.item_type_id = "not_bond"
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        try:
            self.plugin._get_bond_eth_slaves(node, bond_interface)
        except Exception as e:
            self.assertEqual(bootmgr_plugin.BootManagerException, type(e))
            print "Failing!", str(e)

    def test__get_matching_nic_name(self):
        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")
        expected_network = MagicMock()
        expected_network.name = "my_network_name"
        self.plugin = bootmgr_plugin.BootManagerPlugin()
        res = self.plugin._get_matching_nic_name(node, expected_network)
        self.assertEqual(res, None)

        nic = MagicMock(spec=[u'bridge', u'network_name'])
        nic.item_type_id = "bridge"
        nic.device_name = "device.name"
        nic.network_name = "my_network_name"
        node.network_interfaces.append(nic)

        self.plugin._get_bridge_matching_nic = lambda *x: nic
        res = self.plugin._get_matching_nic_name(node, expected_network)
        self.assertEqual(res, nic.device_name)

        nic.item_type_id = "vlan"
        iface = MagicMock()
        iface.item_type_id = "bond"
        slave = MagicMock()
        slave.device_name = "slave_name"
        self.plugin._get_interface_by_name = lambda *x: iface
        self.plugin._get_bond_eth_slaves = lambda *x: [slave]
        res = self.plugin._get_matching_nic_name(node, expected_network)
        self.assertEqual(slave.device_name, res)

        iface.item_type_id = "not_bond"
        iface.device_name = "iface_name"
        self.plugin._get_interface_by_name = lambda *x: iface
        res = self.plugin._get_matching_nic_name(node, expected_network)
        self.assertEqual(iface.device_name, res)

    def test_timeout(self):
        test_time = 1
        timeout = bootmgr_plugin.Timeout(test_time)
        self.assertFalse(timeout.has_elapsed())
        self.assertTrue(0 < timeout.get_elapsed_time())
        self.assertTrue(0 < timeout.get_remaining_time())
        timeout.sleep(test_time)
        self.assertTrue(timeout.has_elapsed())

    def test_wait_for_pxe_boot(self):

        system_name = 'SYS1'
        test_result = ['found']

        timeouts = {'success': 10,
                    'failed': 1}

        class FakeCobbler:
            def find_system(*args):
                return test_result

        def _create_cobbler_client():
            return FakeCobbler()

        bm = bootmgr_plugin.BootManagerPlugin()
        bm._create_cobbler_client = _create_cobbler_client

        node = BootMgrMockNode(item_id="n1",
                               hostname="mn1")

        self.api.is_running = lambda: True

        # Success case
        self.assertTrue(bm._wait_for_pxe_boot(self.api,
                                              node.hostname,
                                              system_name,
                                              timeouts['success']))

        # Failed case
        test_result = []
        self.assertRaises(
            CallbackExecutionException, bm._wait_for_pxe_boot,
            self.api, node.hostname, system_name, timeouts['failed'])

        # Api is not running
        self.api.is_running = lambda: False
        for timeout in timeouts.values():
            self.assertRaises(
                PlanStoppedException, bm._wait_for_pxe_boot,
                self.api, node.hostname, system_name, timeout)

    def test_get_keyboard(self):
        read_data = ['System Locale: LANG=en_IE.UTF-8\n',
                     'VC Keymap: es\n',
                     'X11 Layout: es\n']
        with patch('__builtin__.open') as mock_open:
            mock = MagicMock(spec=file)
            mock.__enter__.return_value.readlines.return_value = read_data
            mock_open.return_value = mock
            self.assertEqual("es", self.testClass._get_keyboard())

    def test_get_keyboard_no_matching_layout(self):
        read_data = ['System Locale: LANG=en_IE.UTF-8\n',
                     'VC Keymap: ie\n',
                     'X11 Layout: ie\n']
        with patch('__builtin__.open') as mock_open:
            mock = MagicMock(spec=file)
            mock.__enter__.return_value.readlines.return_value = read_data
            mock_open.return_value = mock
            self.assertEqual("uk", self.testClass._get_keyboard())

    def test_get_keyboard_no_vc_keymap(self):
        read_data = ['System Locale: LANG=en_IE.UTF-8\n',
                     'X11 Layout: es\n']
        with patch('__builtin__.open') as mock_open:
            mock = MagicMock(spec=file)
            mock.__enter__.return_value.readlines.return_value = read_data
            mock_open.return_value = mock
            self.assertEqual("uk", self.testClass._get_keyboard())

    @patch("__builtin__.open")
    def test_get_keyboard_IOError(self, m_open):
        m_open.side_effect = IOError()
        self.assertEqual("uk", self.testClass._get_keyboard())

    @patch("__builtin__.open")
    def test_get_keyboard_IndexError(self, m_open):
        m_open.side_effect = IndexError()
        self.assertEqual("uk", self.testClass._get_keyboard())

    def test_get_dedicated_pxe_boot_only_nic(self):
        node = BootMgrMockNode(item_id="n1", hostname="mn1")
        eth0 = MagicMock(item_type_id='eth', device_name='eth0')
        eth5 = MagicMock(item_type_id='eth', device_name='eth5')
        node.network_interfaces.extend([eth0, eth5])

        plugin = bootmgr_plugin.BootManagerPlugin()
        dev_name = plugin._get_dedicated_pxe_boot_only_nic(node)
        self.assertTrue(dev_name is None)

        eth5.pxe_boot_only = 'true'
        dev_name = plugin._get_dedicated_pxe_boot_only_nic(node)
        self.assertEquals('eth5', dev_name)

    def test__validate_boot_mode_on_cloud(self):
        # boot_mode=bios
        nodes, service, _ = self._setup_mock_nodes()
        node1 = nodes[0]
        node2 = nodes[1]
        node3 = nodes[2]
        node1.system.disks[0].uuid = None
        node2.system.disks[0].uuid = 'defec8edcafe'
        node3.system.disks[0].uuid = 'kgb'
        errors = self.testClass._validate_boot_mode_on_cloud(nodes, service)
        self.assertTrue(len(errors) == 0)

        # boot_mode=uefi
        ms_system_path = "/infrastructure/systems/system1"
        self.model.update_item(vpath=ms_system_path, boot_mode='uefi')
        service.boot_mode = 'uefi'
        errors = self.testClass._validate_boot_mode_on_cloud(nodes, service)
        self.assertTrue(len(errors) == 1)
        msg = 'UEFI boot_mode is not supported on a Cloud Environment'
        expected = ValidationError(item_path=node3.get_vpath(),
                                   error_message=msg)
        self.assertEqual(expected, errors[0])
