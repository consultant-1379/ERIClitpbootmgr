##############################################################################
# COPYRIGHT Ericsson 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson Inc. The programs may be used and/or copied only with written
# permission from Ericsson Inc. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import math
import os
import re
import time
import xmlrpclib

from netaddr.ip import IPNetwork

from bootmgr_extension.bootmgr_extension import BootManagerExtension
from litp.core.execution_manager import (ConfigTask,
                                         CallbackTask,
                                         CallbackExecutionException,
                                         PlanStoppedException)
from litp.core.extension import ViewError
from litp.core.litp_logging import LitpLogger
from litp.core.plugin import Plugin
from litp.core.rpc_commands import run_rpc_application, \
    RpcCommandProcessorBase, \
    RpcExecutionException, \
    reduce_errs
from litp.core.validators import ValidationError
from .bootmgr_utils import BootMgrUtils

_log = LitpLogger()

UUIDLESSDISK = 'kgb'
COBBLER_API_URL = 'http://127.0.0.1/cobbler_api'
PXE_BOOTED_COMMENT = 'PXE_BOOTED'
COBBLER_MCO_AGENT_TIMEOUT = 55  # this should be the same as cobbler.ddl
COBBLER_RPC_MCO_TIMEOUT = COBBLER_MCO_AGENT_TIMEOUT + 15
# the kickstart keyboard options for the MNs. See here
# https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/6/
# html/Installation_Guide/s1-kickstart2-options.html
KEYMAPS = set(['be-latin1',
               'bg_bds-utf8',
               'bg_pho-utf8',
               'br-abnt2',
               'cf',
               'croat',
               'cz-us-qwertz',
               'cz-lat2',
               'de',
               'de-latin1',
               'de-latin1-nodeadkeys',
               'dvorak',
               'dk',
               'dk-latin1',
               'es',
               'et',
               'fi',
               'fi-latin1',
               'fr',
               'fr-latin9',
               'fr-latin1',
               'fr-pc',
               'fr_CH',
               'fr_CH-latin1',
               'gr',
               'hu',
               'hu101',
               'is-latin1',
               'it',
               'it-ibm',
               'it2',
               'jp106',
               'ko',
               'la-latin1',
               'mk-utf',
               'nl',
               'no',
               'pl2',
               'pt-latin1',
               'ro',
               'ru',
               'sr-cy',
               'sr-latin',
               'sv-latin1',
               'sg',
               'sg-latin1',
               'sk-qwerty',
               'slovene',
               'trq',
               'uk',
               'ua-utf',
               'us-acentos',
               'us'])

UUID_ERR_MESSAGE = """
if [[ ! -b \\${disk_list["%s"]} ]]; then
echo "ERROR: Could not find disk of UUID '%s'" >> /dev/tty1;
read;
exit 1;
fi"""


class Timeout(object):

    def __init__(self, seconds):
        self._wait_for = seconds
        self._start_time = Timeout.time()

    @staticmethod
    def time():
        return time.time()

    @staticmethod
    def sleep(seconds):
        time.sleep(seconds)

    def has_elapsed(self):
        return self.get_elapsed_time() >= self._wait_for

    def get_elapsed_time(self):
        return Timeout.time() - self._start_time

    def get_remaining_time(self):
        return self._wait_for - self.get_elapsed_time()


class BootManagerException(Exception):
    pass


class BootManagerPlugin(Plugin):
    """
    LITP BootManager plugin for Cobbler configuration.
    Cobbler service should be placed under the MS.
    """
    _new_states = ['Initial', 'Applying', 'Updated']
    _max_waiting_time_for_node = 3600  # 1hr
    _boot_size = 1000
    _boot_size_rhel6 = 500
    _uefi_size = 200

    def __init__(self):
        super(BootManagerPlugin, self).__init__()
        self._client = None
        self.token = None

    def create_configuration(self, plugin_api_context):
        """
        Provides support for the addition, update and removal \
        of cobbler-service model items.
        Creating a deployment model with a cobbler-service in the MS \
        allows for the creation of tasks to PXE boot the managed nodes.

        *An example CLI showing creation of cobbler-service \
        model item follow:*

        .. code-block:: bash

            litp create -t cobbler-service -p /ms/services/cobbler

        The boot network should be one of the networks created under \
        /infrastructure and should have the property litp_management set \
        to true. Take a look at the network plugin for further information.
        """

        _log.trace.debug('Creating tasks for cobbler')

        tasks = []

        service = BootManagerExtension._get_cobbler_service(plugin_api_context)

        if service:
            _log.trace.debug(
                'Found cobbler-service: "%s" status: "%s"',
                service,
                service.get_state()
            )

        profiles = plugin_api_context.query("os-profile")
        _log.trace.debug('Found %d os-profiles: %s' % (len(profiles),
                                                       profiles))
        nodes = self._get_new_node_systems(plugin_api_context)
        _log.trace.debug('Got %d "new" nodes : %s' % (len(nodes), nodes))

        ms = plugin_api_context.query("ms")[0]

        self._add_udev_network_tasks(ms, tasks, nodes,
                                     plugin_api_context, service)

        reconfigure_cobbler = False

        for node in nodes:
            if not node.system or not node.storage_profile or \
               not hasattr(node.storage_profile, 'volume_groups'):
                continue

            generate_lvm_kickstart = False
            if (node.system.get_state() in self._new_states) or \
               any(disk.is_initial() or disk.is_updated() \
                   for disk in node.system.disks):
                generate_lvm_kickstart = True
            else:
                for vg in node.storage_profile.volume_groups:
                    if any(fs.is_initial() or fs.is_updated()
                           for fs in vg.file_systems):
                        generate_lvm_kickstart = True

            if node.system.get_state() in self._new_states[0]:
                reconfigure_cobbler = True

            if generate_lvm_kickstart == True:
                self._generate_lvm_kickstart(tasks, node, service)

        if service:
            cobbler_tasks = []
            self._generate_cobbler_kickstart(ms, cobbler_tasks,
                                             nodes, service)
            tasks.extend(cobbler_tasks)
            self._generate_bootloader_fragments(
                plugin_api_context, ms, tasks, nodes, service
            )

            reconfigure = False

            if self._new_ms_network_status(plugin_api_context, ms):
                reconfigure = True

            if service.get_state() in self._new_states or \
                    self._new_ms_network_status(plugin_api_context, ms) or \
                    reconfigure_cobbler:
                self._generate_cobbler_configure(
                    service,
                    plugin_api_context,
                    tasks,
                    reconfigure
                )

            add_node_tasks = []

            self._generate_cobbler_records(
                service,
                plugin_api_context,
                add_node_tasks
            )

            if len(add_node_tasks) == len(cobbler_tasks):
                for i, at in enumerate(add_node_tasks):
                    at.requires.add(cobbler_tasks[i])
            tasks.extend(add_node_tasks)

            self._add_node_wait(
                nodes,
                tasks,
                plugin_api_context,
                service
            )

            _log.trace.debug('Returning %d tasks' % len(tasks))

        return tasks

    def validate_model(self, plugin_api_context):
        """
        Validates cobbler service integrity. Validation rules used in
        this method are:

        - Cobbler service:

          - A unique ``cobbler-service`` instance must exist if there are \
            any nodes in the deployment.

          - All nodes that have to be PXE booted need to have a network with \
            the same name as the network in which cobbler is configured i.e. \
            the network with litp_management set to true.

        - Libvirt:

          - In libvirt systems,the system name in the provider (ms.libvirt) \
            must be the same as in the node system.
        """
        errors = []
        service = self._get_cobbler_service(plugin_api_context)

        nodes = self._nodes_in_the_deployment(plugin_api_context)
        if nodes:
            errors.extend(self._validate_system_exists(nodes))
            errors.extend(self._validate_no_disk_base_items(nodes))
            errors.extend(self._validate_cobbler_service_exists(
                plugin_api_context))
            errors.extend(self._validate_boot_mode_on_cloud(nodes, service))
        if not errors:
            errors.extend(
                self._validate_br_in_libvirt(
                    plugin_api_context,
                    service
                )
            )
            errors.extend(
                self._validate_os_profile(
                    plugin_api_context,
                )
            )

        return errors

    def _validate_system_exists(self, nodes):
        errors = []
        for node in nodes:
            if not node.system:
                msg = "Node {0} doesn't have a system".format(node.hostname)
                errors.append(ValidationError(error_message=msg,
                                              item_path=node.get_vpath()))
        return errors

    def _validate_no_disk_base_items(self, nodes):
        errors = []
        for node in nodes:
            if node.system:
                for disk in node.system.disks:
                    if disk.item_type_id == 'disk-base':
                        msg = 'Node {0} has a disk "{1}" of type "disk-base"'.\
                                format(node.hostname, disk.item_id)
                        errors.append(ValidationError(error_message=msg,
                                                   item_path=disk.get_vpath()))
        return errors

    def _remove_from_cobbler(self, cb_api, nodes, hostname):
        self._do_cobbler_remove_system(cb_api, nodes, hostname)
        self._do_cobbler_mco(cb_api, nodes, 'sync', [])

    def _create_cobbler_client(self):
        return xmlrpclib.Server(COBBLER_API_URL)

    def _has_pxe_completed(self, node_name, cobbler):
        """
        A cobbler pre-install trigger running on MS will set this comment
        as soon as the installation of the node is going to start and
        definitely after PXE boot has finished.
        https://confluence-oss.seli.wh.rnd.internal.ericsson.com/display/ELITP/
        Spike+on+PXE+boot
        """
        try:
            return cobbler.find_system(
                {'name': node_name, 'comment': PXE_BOOTED_COMMENT}
            ) != []
        except xmlrpclib.ProtocolError as err:
            _log.trace.debug('_has_pxe_completed: ' + str(err))

    def _wait_for_pxe_boot(self, callback_api, node_name, system_name,
                           pxe_boot_timeout):

        success = False

        timeout = Timeout(pxe_boot_timeout)

        cobbler_server = self._create_cobbler_client()

        while not success and not timeout.has_elapsed():

            if not callback_api.is_running():
                raise PlanStoppedException(
                    "Plan execution has been stopped on node '%s'." %
                    node_name)

            if int(timeout.get_elapsed_time()) % 60 == 0:
                remaining_time = int(timeout.get_remaining_time())

                _log.trace.debug(
                    "Waiting for node '%s', system '%s', "
                    "to PXE boot (%d sec left)" %
                    (node_name, system_name, remaining_time)
                )

            if self._has_pxe_completed(node_name, cobbler_server):

                elapsed_time = int(timeout.get_elapsed_time())

                _log.trace.debug(
                    "PXE boot successful for node '%s', "
                    "system '%s'. (elapsed time %d sec)" %
                    (node_name, system_name, elapsed_time)
                )

                success = True
            else:
                timeout.sleep(1)

        if not success:
            elapsed_time = int(timeout.get_elapsed_time())

            error_message = ("Node '%s', system '%s', has not PXE booted "
                             "within the specified timeout of %d seconds") % \
                            (node_name, system_name, elapsed_time)

            raise CallbackExecutionException(error_message)

        return success

    def _add_node_wait(self, nodes, tasks, plugin_api_context,
                       cobbler_service):
        boot_network = self._get_boot_network(plugin_api_context)
        # the ms item is mandatory in the model, the [0] should be safe
        ms_hostname = plugin_api_context.query('ms')[0].hostname
        for node in nodes:
            wait_for_pxe_task = CallbackTask(
                node.system,
                'Wait for node "%s" to PXE boot' % node.hostname,
                self._wait_for_pxe_boot,
                node.hostname,
                node.system.system_name,
                int(cobbler_service.pxe_boot_timeout)
            )

            wait_for_pxe_task.model_items.add(cobbler_service)

            wait_for_node_task = CallbackTask(
                node.system,
                'Wait for node "%s" to install and deregister node "%s" ' \
                'from Cobbler' % (node.hostname, node.hostname),
                self._wait_for_node,
                self._find_ip_for_node(node, boot_network),
                node.hostname,
                [ms_hostname],
            )
            wait_for_node_task.requires.add(wait_for_pxe_task)
            tasks.extend([wait_for_node_task, wait_for_pxe_task])

    def _wait_for_node(self, callback_api, node_ip, hostname, nodes):
        self._install_node(callback_api, node_ip, hostname)
        self._remove_from_cobbler(callback_api, nodes, hostname)

    def _add_udev_network_tasks(self, ms, tasks, nodes, plugin_api_context,
                                service):
        for node in nodes:
            _log.trace.debug("Processing node: '%s'" % node)
            net_cards = []

            pxe_boot_only_nic_name = self. \
                _get_dedicated_pxe_boot_only_nic(node)
            if pxe_boot_only_nic_name:
                _log.trace.debug('pxe_boot_only device name "%s"' %
                                 pxe_boot_only_nic_name)
                pxe_boot_only_macaddress = self._find_mac(
                    node,
                    pxe_boot_only_nic_name)
                card = {}
                card['dev'] = pxe_boot_only_nic_name
                card['mac'] = pxe_boot_only_macaddress.lower()
                net_cards.append(card)

            boot_network = self._get_boot_network(plugin_api_context)
            device_name = self._get_matching_nic_name(node, boot_network)
            macaddress = self._find_mac(node, device_name)
            _log.trace.debug(
                'node: "%s" device name: "%s" MAC: "%s"',
                node, device_name, macaddress
            )
            # do not create any udev rules if there is no mac address
            # this will allow the system to generate its own rules
            if macaddress:
                card = {}
                card['dev'] = device_name
                card['mac'] = macaddress.lower()
                net_cards.append(card)

            if net_cards:
                _log.trace.debug("Got MAC cards: '%s'" % net_cards)

            snippet_name = node.hostname + ".ks.udev_network.snippet"
            tasks.append(
                ConfigTask(
                    ms,
                    service,
                    ('Generate UDEV kickstart snippet'
                     ' for node "%s" and NIC(s) "%s"')
                    % (node.hostname, BootManagerPlugin.format_list(
                        [nic['dev'] for nic in net_cards])),
                    "cobbler::udev_network",
                    node.hostname,
                    network_cards=net_cards,
                    path="/var/lib/cobbler/snippets",
                    snippet_name=snippet_name
                )
            )

    def _get_root_vg_disks(self, node):
        the_root_vg = None
        try:
            the_root_vg = node.storage_profile.view_root_vg
        except ViewError as e:
            _log.trace.debug('_get_root_vg_disks' + str(e))

        root_disks = []

        for vg in node.storage_profile.volume_groups:
            if vg.volume_group_name == the_root_vg:
                for pd in vg.physical_devices:
                    for disk in node.system.disks:
                        if disk.name and (disk.name == pd.device_name):
                            root_disks.append(disk)

        return (root_disks, the_root_vg)

    def _subnet_updated(self, network):
        if network.is_updated() and \
                network.applied_properties["subnet"] != network.subnet:
            return True
        return False

    def _new_ms_network_status(self, plugin_api_context, ms):
        networks = plugin_api_context.query("network")
        mgmt_network_names = [network.name for network in networks
                              if network.litp_management == 'true']
        mgmt_networks = [network for network in networks
                         if network.litp_management == 'true']
        statuses = [str(interface.get_state()) for interface
                    in ms.network_interfaces if interface.network_name
                    in mgmt_network_names]

        statuses.extend([str(net.get_state()) for net
                         in mgmt_networks if self._subnet_updated(net)])
        return any(status in self._new_states for status in statuses)

    def _get_system_disk(self, node):
        # TODO : check if this is correct! why the first disk?
        for disk in node.system.disks:
            return disk
        return None

    def _get_all_disk_uuids(self, api):
        all_uuids = []
        for node in iter(self._get_all_node_systems(api)):
            for disk in node.system.disks:
                all_uuids.append(disk.uuid)
        return all_uuids

    def _generate_bootloader_fragments(self, api, ms, tasks, nodes, service):
        _log.trace.debug("_generate_bootloader_fragments.  Nodes: %s" % \
                         str(nodes))

        all_uuids = self._get_all_disk_uuids(api)
        for node in nodes:
            hostname = node.hostname

            if not len(node.system.disks):
                _log.trace.debug("No disks found on node %s" % hostname)
                continue
            # We know which one of the disks in the node's system's collection
            # is marked as bootable. We'll trust that this information is
            # accurate and pass this device to the 'bootloader' Anaconda
            # command
            # NOTE: The presence of one (and exactly ONE) boot disk is enforced
            # by model validation in ERIClitpvolmgr
            #
            # NOTE: The boot disk *is not necessarily* the disk on which we
            # create the boot partition!!!
            #
            # The boot partition is known to Grub as the 'root'
            disk = None
            boot_disk = [disk for disk in node.system.disks \
                         if 'true' == disk.bootable][0]

            shared_disks = [d.uuid for d in node.system.disks if \
                            all_uuids.count(d.uuid) > 1]

            if self._is_os_reinstall(node):
                shared_disks.extend(
                    [disk.uuid for disk in node.system.disks
                     if (disk.bootable == 'false' and
                     (hasattr(disk, 'shared') and disk.shared == 'true'))
                     and disk.uuid not in shared_disks])

            # If the node is in a deployment with fencing disks, add the
            # fencing disks uuids to the shared_disks parameter to prevent
            # wiping disk on pxe boot
            all_clusters = node.get_cluster().parent
            for cluster in all_clusters:
                if cluster.item_type.item_type_id == 'vcs-cluster':
                    shared_disks.extend([fen_disk.uuid for fen_disk
                                         in cluster.fencing_disks])

            if (BootManagerPlugin._is_uuid_plugin_updatable(boot_disk) or
                    BootManagerPlugin._uuid_on_disk(boot_disk)):
                _log.trace.debug("Boot disk for node {name} is identified by "
                                 "uuid {id}".format(
                    name=hostname, id=disk.uuid))
                uuid_prop = BootMgrUtils.get_disk_uuid(boot_disk)

                _log.trace.debug('Passing shared_disks argument: '
                                 '"{shared_disks}" to ConfigTask'.format(
                    shared_disks=shared_disks))
                task = ConfigTask(
                    ms,
                    service,
                    'Generate "%s" bootloader kickstart snippet for '
                    'node "%s"' % (node.os.version.upper(),
                                   node.hostname),
                    "cobbler::bootloader",
                    node.hostname,
                    boot_disk_uuid=uuid_prop,
                    snippet_name=hostname + ".ks.bootloader.snippet",
                    shared_uuids=shared_disks,
                    os_version=node.os.version
                )
                task.requires.add(boot_disk.get_source())
                task.replaces.add(("cobbler::bootloader_name", node.hostname))
                tasks.append(task)
            else:
                _log.trace.debug("Boot disk for node {name} is identified by "
                                 "device name {disk_name}".format(
                    name=hostname,
                    disk_name=disk.name
                )
                )
                tasks.append(
                    ConfigTask(
                        ms,
                        service,
                        'Generate "%s" bootloader kickstart snippet for '
                        'node "%s"' % (node.os.version.upper(),
                                       node.hostname),
                        "cobbler::bootloader_name",
                        node.hostname,
                        boot_disk_uuid=boot_disk.uuid,
                        boot_disk_name=boot_disk.name,
                        snippet_name=hostname + ".ks.bootloader.snippet",
                        os_version=node.os.version
                    )
                )

    @staticmethod
    def _get_shared_uuids(node, all_uuids):
        return [d.uuid for d in node.system.disks if \
                all_uuids.count(d.uuid) > 1]

    @staticmethod
    def _is_uuid_plugin_updatable(disk):
        uuid_prop = disk.item_type.structure.get("uuid")
        if uuid_prop:
            return uuid_prop.updatable_plugin
        return False

    @staticmethod
    def _uuid_on_disk(disk_query_item):
        return disk_query_item.uuid and \
               UUIDLESSDISK != disk_query_item.uuid.strip().lower()

    @staticmethod
    def _get_add_lvm_conf(node):
        return any([True for disk in node.system.disks if
                    'true' == disk.bootable and
                    disk.item_type_id not in ['disk', 'disk-base']])

    @staticmethod
    def format_list(lst, quotes_char='none'):
        if lst:
            char = {'single': '\'', 'double': '\"'}
            qmark = char.get(quotes_char, '')
            t0 = qmark + "%s" + qmark
            t1 = t0 + ", "
            t2 = t0 + " and "
            template = t1 * len(lst[:-2]) + t2 * len(lst[-2:-1]) + t0
            return template % tuple(lst)
        return ""

    def _generate_lvm_kickstart(self, tasks, node, service):
        """
        This method generates a CallbackTask that will write a snippet to the
        MS filesystem with the install-time storage configuration for each node
        in ``nodes``.
        """

        _log.trace.debug("_generate_lvm_kickstart. Node: %s" % node.hostname)

        if not len(node.system.disks):
            _log.trace.debug("No disks found on node %s" % node.hostname)
            return

        # Create CallbackTask to create the snippet for each node
        path = "/var/lib/cobbler/snippets/%s.ks.partition.snippet" % \
               node.hostname

        # Associate task with 'cobbler-service' on ms
        _log.trace.debug("Adding callback task, node %s" % node.hostname)
        task = CallbackTask(service,
                            ('Create "%s" partition kickstart snippet for '
                             'node "%s"') % (node.os.version.upper(),
                                             node.hostname),
                            self.cb__write_snippet,
                            path=path,
                            node_hostname=node.hostname,
                            os_version=node.os.version,
                            boot_mode=service.boot_mode)
        tasks.append(task)

    def _get_disk_list_item_config(self, disk, all_disk_uuids):
        config = []
        _log.event.info("Get disk list item for {0} "
                        "with all_disk_uuids {1}".format(
            disk.item_id, all_disk_uuids))
        if BootManagerPlugin._uuid_on_disk(disk):
            # Add all disks that aren't shared across systems to the set
            # passed to Anaconda's clearpart command (the order doesn't
            # matter).
            # It is assumed UUID-less disks are never shared.
            if all_disk_uuids.count(disk.uuid) != 1:
                return config

            # Fallback for HP SmartArray (LITPCDS-8098). Assumes that if
            # there is a mix of scsi and cciss block devices, the disks
            # themselves are only pointed to by one of them.

            diskstr = """\
disk_list_item=\\$(shopt -s nocaseglob; \
ls /dev/disk/by-id/dm-uuid-mpath*{uuid})
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\\$(shopt -s nocaseglob; ls /dev/disk/by-id/cciss*{uuid})
fi
if [ ! -n "$disk_list_item" ]; then
disk_list_item=\\$(shopt -s nocaseglob; ls /dev/disk/by-id/scsi*{uuid})
fi
disk_list["{disk_id}"]=\\$disk_list_item"""
            config.append(diskstr.format(uuid=disk.uuid, disk_id=disk.item_id))
            test = UUID_ERR_MESSAGE % (disk.item_id, disk.uuid)
            config.append(test)
        else:
            _log.event.info("Disk {0} has no uuid".format(disk.item_id))
            # We don't want to set the key's value to /dev/<disk.name>
            # since we want to handle the case where there is no device
            # by that name on the node
            config.append('disk_list["{disk_id}"]=\\$(shopt -s '
                          'nocaseglob; ls /dev/{name})'.format(
                disk_id=disk.item_id,
                name=disk.name
            ))
        return config

    def _get_clearpart_config(self, disk):
        _log.event.info("Generate clearpart config for disk {0}".format(
                        disk.item_id))
        if BootManagerPlugin._uuid_on_disk(disk):
            _log.event.info("Generate three-try drive_dev")
            devstr = """\
#### clear parts first ####
parts_to_clear=\\$(find /dev/disk/by-id \
-iname dm-uuid-part*-mpath\\*{uuid} -printf "disk/by-id/%f,")
drive_dev=\\$(find /dev/disk/by-id \
-iname dm-uuid-mpath\\*{uuid} -printf "disk/by-id/%f")
if [ ! -n "$drive_dev" ] || [ "$drive_dev" == "disk/by-id/" ]; then
drive_dev=\\$(basename \
\\$(find /dev/disk/by-id -iname cciss\\*{uuid} -printf "%l"))
fi
if [ ! -n "$drive_dev" ] || [ "$drive_dev" == "disk/by-id/" ]; then
drive_dev=\\$(basename \
\\$(find /dev/disk/by-id -iname scsi\\*{uuid} -printf "%l"))
fi"""
            config = devstr.format(uuid=disk.uuid)
        else:
            _log.event.info("Generate drive_dev for disk {0}".format(
                disk.item_id))
            config = "drive_dev={0}\n".format(disk.name)
        return config

    def _is_bootable_unshared_and_os_reinstall(self, node, disk, shared_uuids):
        return disk.uuid not in shared_uuids and \
                 (self._is_os_reinstall(node) and
                  'true' == disk.bootable)

    def _get_disks_to_clear(self, node, all_disk_uuids, boot_mode):
        config = []
        shared_uuids = BootManagerPlugin._get_shared_uuids(
            node, all_disk_uuids)
        for disk in node.system.disks:
            _log.event.info("Getting configs for disk"
                            " {0} on {1}".format(disk.item_id, node))
            config.extend(self._get_disk_list_item_config(
                disk, all_disk_uuids))
            if 'true' == disk.bootable or \
                    self._is_bootable_unshared_and_os_reinstall(
                        node, disk, shared_uuids):
                config.append(self._get_clearpart_config(disk))
                config.append(
                    '\nclearpart_devs=\\${clearpart_devs},\\${drive_dev}'
                )
            else:
                _log.event.info("No clearpart for disk_list_item_config for"
                                " disk {0} uuid={1} and bootable={2} "
                                "and os_reinstall={3}".format(
                    disk.item_id, disk.uuid, disk.bootable,
                    self._is_os_reinstall(node)))
        _log.event.info("Add drive drive_dev to clearpart_devs ")
        if self._is_os_reinstall(node):
            config.append(
                "vgchange -an vg_root --force\n"
                "for pv_dev in \\$(pvs | grep vg_root | "
                "awk '{print \\$1}'); do\n"
                "vgreduce --force --yes vg_root $pv_dev --force\n"
                "pvremove --force --yes $pv_dev --force\n"
                "done;\n"
                "vgremove --force --yes vg_root --force\n")
        else:
            config.append(
                "for vg in \\$(vgs --no-headings | awk '{print \\$1}'); do\n"
                "vgchange -an $vg --force\n"
                "vgreduce --removemissing $vg\n"
                "for pv_dev in \\$(pvs | grep $vg | awk '{print \\$1}'); do\n"
                "vgreduce --force --yes $vg $pv_dev --force\n"
                "pvremove --force --yes $pv_dev --force\n"
                "done;\n"
                "vgremove --force --yes $vg --force\n"
                "done;\n")
        # Write the clearpart invocation to the file %included from the
        # Kickstart at runtime
        # TORF-512209 - but only if the disk is bootable
        part_table_type = "gpt" if boot_mode == "uefi" else "msdos"
        config.append(
            'if [ "\\${{#parts_to_clear}}" -gt 2 ]; then\n'
            'IFS=\',\' read -r -a wipedisks <<< '
            '"$clearpart_devs,$parts_to_clear"\n'
            'else\n'
            'IFS=\',\' read -r -a wipedisks <<< '
            '"$clearpart_devs"\n'
            'fi\n'
            'for wipedisk in \\${{wipedisks[@]}}; do\n'
            'partprobe /dev/"$wipedisk"\n'
            'wipefs -qfa /dev/"$wipedisk"\n'
            'udevadm settle\n'
            'sleep 2s\n'
            'partprobe /dev/"$wipedisk"\n'
            'udevadm settle\n'
            'sleep 2s\n'
            'parted /dev/"$wipedisk" '
            '--script -- mklabel {0}\n'
            'done\n'.format(part_table_type))
        return config

    def _get_optional_partitions(self, disk, boot_mode):
        opt_part_commands = []
        if boot_mode == 'uefi':
            opt_part_commands.append(
                "echo \"part /boot/efi --fstype=efi --size=%s "
                "--ondisk=${disk_list[\"%s\"]}\" >>"
                " /tmp/partitioninfo" % (
                    self._uefi_size,
                    disk.item_id
                )
            )
        else:
            # TORF-495707: Add a 1MB biosboot partition in the case the
            # underlying phsical disk is >= 2TB. See grub2/gpt
            # partitioning in RHEL7.
            # TORF-544812: In all other cases, add a mock 1MB biosboot
            # partition to keep discovery of the correct partition to
            # write on simple.
            opt_part_commands.append(
                'dev_path=\\$(realpath "/dev/"\\${drive_dev})\n'
                'dev_name=\\$(basename "${dev_path}")\n'
                'dev_size=\\$(cat "/sys/block/${dev_name}/size")\n'
                'disk_size=\\$(( 512 * $dev_size / 1024**4 ))\n'
                'if [[ "${disk_size}" -ge 2 ]]; then\n'
                'echo "part biosboot --fstype=biosboot'
                ' --size=1 --ondisk=${disk_list["%s"]}\" >> '
                '/tmp/partitioninfo\nelse\n'
                'echo "part extra --fstype=ext4 --size=1'
                ' --ondisk=${disk_list["%s"]}\" >> '
                '/tmp/partitioninfo\n'
                'fi' % (disk.item_id, disk.item_id))

        return opt_part_commands

    def _get_node_boot_parts(self, node, all_disk_uuids, boot_mode):
        boot_part_commands = list()
        for disk in node.system.disks:
            # Add all disks that aren't shared across systems to the set
            # passed to Anaconda's clearpart command (the order doesn't
            # matter).
            # It is assumed UUID-less disks are never shared.
            _log.event.info("Skip disk {0} uuid={1} uuid_on_disk={2}".format(
                disk, disk.uuid, BootManagerPlugin._uuid_on_disk(disk)))
            if all_disk_uuids.count(disk.uuid) != 1 and \
                BootManagerPlugin._uuid_on_disk(disk):
                continue

            if 'true' == disk.bootable:
                boot_part_commands.extend(
                    self._get_optional_partitions(disk, boot_mode))

                boot_part_commands.append(
                    "echo \"part /boot --fstype=xfs --size=%s " \
                    "--ondisk=${disk_list[\"%s\"]}\" >> " \
                    "/tmp/partitioninfo" % (
                        self._boot_size,
                        disk.item_id,
                    )
                )

        return boot_part_commands

    def _get_node_volume_parts(self, node, root_disks, root_vg):
        config = []
        for vg in node.storage_profile.volume_groups:
            if vg.volume_group_name != root_vg:
                continue

            # Write the 'part' invocation for the Root VG's backing
            # Physical Volume to the file %included from the Kickstart at
            # runtime
            root_vg_part_index = 1
            part_ids = []
            config.append('# Create PV(s) for Root VG')
            for root_disk in root_disks:
                part_id = "pv.0%d%s" % \
                          (root_vg_part_index, vg.volume_group_name)
                # I'd expect IDs like pv.01root_vg, pv.02root_vg, ...
                part_ids.append(part_id)

                line = ("echo \"part %s --size=1000 --grow" % (part_id)) + \
                       (" --ondisk=${disk_list[\"%s\"]}\"" % \
                        root_disk.item_id) + \
                       " >> /tmp/partitioninfo"
                config.append(line)
                root_vg_part_index += 1

            config.append('# Create Root VG')
            # Write the 'volgroup' invocation for the Root VG to the file
            # %included from the Kickstart at runtime
            line = ("echo \"volgroup %s" % vg.volume_group_name) + \
                   (" --pesize=4096 %s\" >> /tmp/partitioninfo" % \
                    ' '.join(part_ids))
            config.append(line)

            config.append('# Create Root VG Logical Volumes')
            for file_system in vg.file_systems:
                if file_system.mount_point:
                    line = "echo \"logvol %s --fstype=%s" % (
                        file_system.mount_point, file_system.type)
                    line += " --name=%s --vgname=%s " % (
                        "_".join((vg.item_id, file_system.item_id)),
                        vg.volume_group_name)
                    fs_size = self._convert_to_mb(file_system.size)
                    if '/' == file_system.mount_point:
                        line += "--size=1000 --grow --maxsize=%s" % fs_size
                    else:
                        line += "--size=%s" % fs_size
                    line += "\" >> /tmp/partitioninfo"
                    config.append(line)

        return config

    def _get_lvm_kickstart_config(self, api, node_hostname, boot_mode):
        all_disk_uuids = self._get_all_disk_uuids(api)
        node = api.query("node", hostname=node_hostname)[0]
        _log.event.info("Generate {0} LVM Kickstart config".format(
            node.os.version))

        config = ["# Hash map",
                  "declare -A disk_list",
                  "# Loop through the data structure we have been" + \
                  " passed in and build up a bash",
                  "# hash of device paths based on uuid. " + \
                  "Clear all disks in the model",
                  "declare -a clearpart_devs",
                  "declare -a parts_to_clear"]
        root_disks, root_vg = self._get_root_vg_disks(node)

        if root_disks == []:
            return

        config.extend(self._get_disks_to_clear(node, all_disk_uuids,
                                               boot_mode))

        config.append('echo "clearpart --all --drives='
                      '\\${clearpart_devs/#,/}">/tmp/partitioninfo')
        config.append('echo "ignoredisk --only-use='
                      '\\${clearpart_devs/#,/}">>/tmp/partitioninfo')
        config.append('echo "zerombr">>/tmp/partitioninfo')

        config.append('# Second loop to generate the partition '
                      'tables - NB. must be after the clearpart '
                      'command - hence 2 loops')

        # FIXME So what if the root VG is *NOT* backed by the one bootable
        # disk? What happens then?
        # Well, grub (as installed by Anaconda) is cool with having a Grub
        # root (ie. the partition on which stage2, grub.conf and the
        # kernels live) on a *different* disk to where the stage1 is
        # written. The only problem is that this drive may not be reachable
        # from stage1 if it's not local.
        # TODO Maybe we should *always* write the Grub root (== /boot) on
        # the boot drive where the stage1 will live
        config.extend(self._get_node_boot_parts(node, all_disk_uuids,
                                                boot_mode))
        config.extend(self._get_node_volume_parts(node, root_disks, root_vg))

        return config

    @staticmethod
    def _is_os_reinstall(node):
        return hasattr(node, "upgrade") and \
               hasattr(node.upgrade, "os_reinstall") and \
               node.upgrade.os_reinstall == 'true'

    def _get_rhel6_disk_config(self, api, disk, config, boot_part_commands):
        all_disk_uuids = self._get_all_disk_uuids(api)

        # Build a hash mapping disk uuids to their symlinks in
        # /dev/disk/by-id
        if BootManagerPlugin._uuid_on_disk(disk):
            # Add all disks that aren't shared across systems to the set
            # passed to Anaconda's clearpart command (the order doesn't
            # matter).
            # It is assumed UUID-less disks are never shared.
            if all_disk_uuids.count(disk.uuid) != 1:
                return config, boot_part_commands
            config.append('disk_list_item=\\$(shopt -s '
                          'nocaseglob; ls /dev/disk/by-id/scsi*{uuid}'
                          ')'.format(
                uuid=disk.uuid
            )
            )
            # Fallback for HP SmartArray (LITPCDS-8098). Assumes that if
            # there is a mix of scsi and cciss block devices, the disks
            # themselves are only pointed to by one of them.
            config.append(
                'if [ ! -n "$disk_list_item" ]; then\n'
                'disk_list_item=\\$(shopt -s nocaseglob; '
                'ls /dev/disk/by-id/cciss*{uuid}'
                ')\nfi'.format(
                    uuid=disk.uuid
                )
            )
            config.append(
                'disk_list["{disk_id}"]=\\$disk_list_item'.format(
                    disk_id=disk.item_id
                )
            )
            test = """
if [[ ! -b \\${disk_list["%s"]} ]]; then
echo "ERROR: Could not find disk of UUID '%s'" >> /dev/tty1;
read;
exit 1;
fi""" % (disk.item_id, disk.uuid)
            config.append(test)
        else:
            # We don't want to set the key's value to /dev/<disk.name>
            # since we want to handle the case where there is no device
            # by that name on the node
            config.append('disk_list["{disk_id}"]=\\$(shopt -s '
                          'nocaseglob; ls /dev/{name})'.format(
                disk_id=disk.item_id,
                name=disk.name
            ))

        if BootManagerPlugin._uuid_on_disk(disk):
            config.append('drive_dev=\\$(basename \\$(find '
                          '/dev/disk/by-id -iname scsi\\*%s -printf "%%l"))'
                          % (disk.uuid)
                          )
            # Fallback for HP SmartArray (LITPCDS-8098).
            config.append(
                'if [ ! -n "$drive_dev" ]; then\n'
                'drive_dev=\\$(basename \\$(find '
                '/dev/disk/by-id -iname cciss\\*%s -printf "%%l"))\n'
                'fi'
                % (disk.uuid)
            )
        else:
            config.append('drive_dev={0}'.format(disk.name))

        config.append('clearpart_devs=\\${clearpart_devs},'
                      '\\${drive_dev}')

        if 'true' == disk.bootable:
            boot_part_commands.append(
                "echo \"part /boot --fstype=ext4 --size=%s " \
                "--ondisk=${disk_list[\"%s\"]}\" >>" \
                "/tmp/partitioninfo" % (
                    self._boot_size_rhel6,
                    disk.item_id,
                )
            )
        return config, boot_part_commands

    def _get_lvm_kickstart_config_rhel6(self, api, node_hostname):
        node = api.query("node", hostname=node_hostname)[0]
        config = ["# Hash map",
                  "declare -A disk_list",
                  "# Loop through the data structure we have been" + \
                  " passed in and build up a bash",
                  "# hash of device paths based on uuid. " + \
                  "Clear all disks in the model"]

        root_disks, root_vg = self._get_root_vg_disks(node)

        if root_disks == []:
            return

        boot_part_commands = list()
        for disk in node.system.disks:
            config, boot_part_commands = self._get_rhel6_disk_config(
                api, disk, config, boot_part_commands)

        # Write the clearpart invocation to the file %included from the
        # Kickstart at runtime
        config.append('echo "clearpart --initlabel --all --drives=' +
                      '\\${clearpart_devs/#,/}">/tmp/partitioninfo')

        config.append("# Second loop to generate the partition " +
                      "tables - NB. must be after the clearpart " +
                      "command - hence 2 loops")

        # So what if the root VG is *NOT* backed by the one bootable
        # disk? What happens then?
        # Well, grub (as installed by Anaconda) is cool with having a Grub
        # root (ie. the partition on which stage2, grub.conf and the
        # kernels live) on a *different* disk to where the stage1 is
        # written. The only problem is that this drive may not be reachable
        # from stage1 if it's not local.
        # TODO Maybe we should *always* write the Grub root (== /boot) on
        # the boot drive where the stage1 will live
        config.extend(boot_part_commands)

        for vg in node.storage_profile.volume_groups:
            if vg.volume_group_name != root_vg:
                continue

            # Write the 'part' invocation for the Root VG's backing
            # Physical Volume to the file %included from the Kickstart at
            # runtime
            root_vg_part_index = 1
            part_ids = []
            config.append('# Create PV(s) for Root VG')
            for root_disk in root_disks:
                part_size = self._convert_to_mb(root_disk.size)
                if 'true' == root_disk.bootable:
                    part_size -= self._boot_size_rhel6

                part_id = "pv.0%d%s" % \
                          (root_vg_part_index, vg.volume_group_name)
                # I'd expect IDs like pv.01root_vg, pv.02root_vg, ...
                part_ids.append(part_id)

                line = ("echo \"part %s --size=%s" % (part_id, part_size)) + \
                       (" --ondisk=${disk_list[\"%s\"]}\"" % \
                        root_disk.item_id) + \
                       " >> /tmp/partitioninfo"
                config.append(line)
                root_vg_part_index += 1

            config.append('# Create Root VG')
            # Write the 'volgroup' invocation for the Root VG to the file
            # %included from the Kickstart at runtime
            line = ("echo \"volgroup %s" % vg.volume_group_name) + \
                   (" --pesize=4096 %s\" >> /tmp/partitioninfo" % \
                    ' '.join(part_ids))
            config.append(line)

            config.append('# Create Root VG Logical Volumes')
            for file_system in vg.file_systems:
                if file_system.mount_point:
                    line = "echo \"logvol %s --fstype=%s" % (
                        file_system.mount_point, file_system.type)
                    line += " --name=%s --vgname=%s --size=%s" % (
                        "_".join((vg.item_id, file_system.item_id)),
                        vg.volume_group_name,
                        self._convert_to_mb(file_system.size))
                    line += "\" >> /tmp/partitioninfo"
                    config.append(line)
        return config

    @staticmethod
    def _convert_to_mb(size):
        for i in zip(range(3), ['M', 'G', 'T']):
            if size[-1] == i[1]:
                return int(size[:-1]) * 1024 ** i[0]

    def _get_keyboard(self):
        """
        @summary: Picks up the keyboard layout from the MS
        """
        localectl_out = '/opt/ericsson/nms/litp/share/kickstart/localectl.out'
        default_layout = 'uk'
        kb_layout = None
        try:
            with open(localectl_out, 'r') as f:
                output = f.readlines()
            for line in output:
                if "VC Keymap:" in line:
                    kb_layout = line.split(":", 1)[-1]
                    kb_layout = kb_layout.strip(" ")
                    kb_layout = kb_layout.strip("\n")
                    break
            if kb_layout not in KEYMAPS:
                _log.trace.error(
                    "Keyboard layout {0} is not supported by "
                    "kickstart. Using default {1} instead".
                        format(kb_layout, default_layout)
                )
                return default_layout
            return kb_layout
        except (IndexError, IOError) as err:
            _log.trace.error(
                "{0}. "
                "Using default {1} instead".
                    format(err, default_layout)
            )
            return default_layout

    def _get_lvm_disk_uuids_for_node(self, node):
        lvm_disk_uuids = []
        if node.storage_profile.volume_driver == 'lvm':
            for vg in node.storage_profile.volume_groups:
                pds = [pd for pd in vg.physical_devices]
                lvm_disk_uuids.extend(BootMgrUtils.get_disks_for_pds(pds,
                                                                     node))

        return lvm_disk_uuids

    @staticmethod
    def _is_openstack_env(ms):
        return any([('enm_deployment_type' == gprop.key and
                     'vLITP_ENM_On_Rack_Servers' == gprop.value)
                    for cmngr in ms.query('config-manager')
                    for gprop in cmngr.global_properties])

    def _generate_cobbler_kickstart(self, ms, tasks, nodes, service):
        openstack_env = BootManagerPlugin._is_openstack_env(ms)

        ms_hostname = ms.hostname
        for node in nodes:
            cluster_type = ""
            cluster = node.get_cluster()
            if hasattr(cluster, "cluster_type"):
                cluster_type = cluster.cluster_type

            include_statement = ""
            if len(node.system.disks):
                include_statement = "%include /tmp/partitioninfo"

            selinux_mode = service.ksm_selinux_mode
            os_reinstall = BootManagerPlugin._is_os_reinstall(node)

            if os_reinstall and 'sfha' == cluster_type:
                selinux_mode = 'disabled'

            lvm_disk_uuids = []
            if 'sfha' == cluster_type and 'uefi' == service.boot_mode:
                lvm_disk_uuids = self._get_lvm_disk_uuids_for_node(node)

            add_lvm_conf = BootManagerPlugin._get_add_lvm_conf(node)

            tasks.append(
                ConfigTask(
                    ms,
                    service,
                    ('Generate "%s" Cobbler kickstart file '
                     'for node "%s"') % (node.os.version.upper(),
                                         node.hostname),
                    "cobbler::kickstart",
                    node.hostname,
                    selinux_mode=selinux_mode,
                    path=service.ksm_path,
                    ksname=node.hostname + '.ks',
                    timezone=self._get_timezone(),
                    keyboard=self._get_keyboard(),
                    partitioninfo=str(include_statement),
                    cluster_type=cluster_type,
                    ms_hostname=ms_hostname,
                    os_version=node.os.version,
                    os_reinstall=str(os_reinstall).lower(),
                    boot_mode=service.boot_mode,
                    add_lvm_conf=str(add_lvm_conf).lower(),
                    lvm_uuids=lvm_disk_uuids,
                    openstack_env=str(openstack_env).lower(),
                )
            )

    def _get_boot_network(self, plugin_api_context):
        boot_net = [network for network in
                    plugin_api_context.query("network", litp_management='true')
                    if not (network.is_removed() or network.is_for_removal())
                    ][0]
        return boot_net

    def _generate_cobbler_configure(self, service, plugin_api_context,
                                    tasks, reconfigure):
        boot_net = self._get_boot_network(plugin_api_context)
        ms = plugin_api_context.query("ms")[0]
        networks = []
        networks.append(self._network_dict(boot_net))
        rem_old_pup = 1 if \
            service.remove_old_puppet_certs_automatically == "true" else 0
        sign_pupp_certs = 1 if \
            service.sign_puppet_certs_automatically == "true" else 0
        puppet_auto_setup = 1 if \
            service.puppet_auto_setup == "true" else 0
        rsync_disabled = 'yes' if \
            service.rsync_disabled == "true" else 'no'

        self._find_ip_for_node(ms, boot_net)

        if reconfigure:
            task_description = 'Reconfigure Cobbler server on node'
        else:
            task_description = 'Create Cobbler server on node'

        os_profile = plugin_api_context.query("os-profile")[0]
        distro_name = "%s-%s" % (os_profile.name, os_profile.arch)

        config_task = ConfigTask(
            ms,
            service,
            '%s "%s"' % (task_description, ms.hostname),
            "cobbler::configure", "bootservice_cfg",
            manage_dns=1 if service.manage_dns == "true" else 0,
            manage_dhcp=1 if service.manage_dhcp == "true" else 0,
            server=self._find_ip_for_node(ms, boot_net),
            authentication=service.authentication,
            remove_old_puppet_certs_automatically=rem_old_pup,
            sign_puppet_certs_automatically=sign_pupp_certs,
            puppet_auto_setup=puppet_auto_setup,
            rsync_disabled=rsync_disabled,
            networks=networks,
            boot_mode=service.boot_mode,
            distro=distro_name
        )

        tasks.append(config_task)

    def _network_dict(self, network_item):
        if network_item.subnet:
            network = IPNetwork(network_item.subnet)
            subnet = network.cidr.ip
            netmask = network.cidr.netmask
            # This dictionary is used by the cobbler::configure Puppet
            # resource to configure the DHCP server used for node installs
            #
            # We do not supply installing nodes with a default route.
            netdict = dict(
                subnet=str(subnet),
                netmask=str(netmask),
            )
            return netdict
        else:
            return None

    def _get_all_node_systems(self, plugin_api_context):
        return [n for n in plugin_api_context.query(
            "node",
            is_for_removal=False
        )
                if not n.system.is_removed() and not n.system.is_for_removal()]

    def _get_new_node_systems(self, plugin_api_context):
        nodes = plugin_api_context.query("node", is_for_removal=False)

        nodes = [n for n in nodes
                 if n.system.get_state() in self._new_states]
        return nodes

    def _generate_cobbler_records(self, service, plugin_api_context,
                                  tasks):

        def create_profile_task(ms, service, version,
                                distro_name, post_opts, opts):

            def_ks_path = '/var/lib/cobbler/kickstarts/default.ks'
            return ConfigTask(ms, service,
                              'Add "%s" profile "%s"' % (version.upper(),
                                                         distro_name),
                              'cobblerdata::add_profile',
                              distro_name,
                              distro=distro_name,
                              kickstart=def_ks_path,
                              ks_opts_post=post_opts,
                              kopts=opts,
                              repos=[])

        profiles = plugin_api_context.query("os-profile", is_initial=True)

        ms = plugin_api_context.query("ms")[0]
        providers = self._get_providers(plugin_api_context)
        new_node_systems = self._get_new_node_systems(plugin_api_context)
        _log.trace.debug('Profiles to be set up: %s' % profiles)
        _log.trace.debug('New systems to be set up: %s' % new_node_systems)

        WEB_ROOT = '/var/www/html/'
        profile_tasks = {}
        for profile in profiles:
            distro_name = "%s-%s" % (profile.name, profile.arch)

            task_args = {
                'path': profile.path,
                'breed': profile.breed,
                'os_version': profile.version,
                'arch': profile.arch,
            }

            # If the path is already available over HTTP, tell Cobbler about
            # that so that it doesn't copy the entire directory tree
            # (See http://jira-oss.lmera.ericsson.se/browse/LITPCDS-8291)

            if profile.path.startswith(WEB_ROOT):
                task_args['url_path'] = profile.path[len(WEB_ROOT):]

            import_distro_task = ConfigTask(
                ms,
                service,
                'Import "%s" distro "%s"' % (profile.version.upper(),
                                             distro_name),
                "cobblerdata::import_distro",
                distro_name,
                **task_args
            )
            tasks.append(import_distro_task)
            # profile.kopts_post: a=b,c d=e,f
            args = [arg.strip() for arg in
                    profile.kopts_post.split(" ") if arg]
            args = [arg.split("=", 1) for arg in args]
            args = [(key.strip(), value.strip()) for key, value in args]
            ks_opts_post = dict(args)
            # ks_opts_post: {"a": "b,c", "d": "e,f"}

            kopts = self._get_kernel_options(profile.version)

            profile_task = create_profile_task(ms, service,
                                               profile.version, distro_name,
                                               ks_opts_post, kopts)

            profile_tasks[distro_name] = profile_task
            profile_task.requires.add(import_distro_task)
            tasks.append(profile_task)

        if new_node_systems:
            for node in new_node_systems:
                _log.trace.debug('Call create_sys_parms for node "%s"' % node)
            new_systems = [self._create_system_params(
                node, service, providers,
                plugin_api_context) for node in new_node_systems]
            for system_params in new_systems:
                add_system_task = CallbackTask(
                    service,
                    'Register system "%s" for install' % system_params['name'],
                    self._add_system_callback,
                    [ms.hostname],
                    system_params['name'],
                    profile=system_params['profile'],
                    interfaces=system_params['interfaces'],
                    hostname=system_params['name'],
                    kickstart="/var/lib/cobbler/kickstarts/%s.ks"
                              % system_params['name'],
                    virt_data=system_params['virt_data']
                )
                system_profile_task = None
                if profile_tasks:
                    system_profile_task = profile_tasks.get( \
                        system_params['profile'])

                if system_profile_task:
                    add_system_task.requires.add(system_profile_task)
                tasks.append(add_system_task)

    def _get_kernel_options(self, os_version):
        _log.event.debug("Add {0} kernel options".format(os_version))

        if os_version == "rhel6":
            # RHEL 6 kernel options
            kopts = \
                {
                    'inst.repo': 'http://@@http_server@@/6/os/x86_64/',
                }
        else:
            # RHEL 7 kernel options
            kopts = \
                {
                    'inst.repo': 'http://@@http_server@@/7/os/x86_64/',
                    'ksdevice': '',
                    'net.ifnames': '0'
                }
        return kopts

    def _do_cobbler_mco(self, cb_api, nodes, cmd, cmd_args,
                        timeout=COBBLER_RPC_MCO_TIMEOUT):
        # A default timeout (COBBLER_RPC_MCO_TIMEOUT) is set for the rpc
        # command. The timeout should not be less than the cobbler mco agent
        # timeout, so we can receive potential timeout errors from mco.
        assert timeout > COBBLER_MCO_AGENT_TIMEOUT, \
            "RPC timeout should be larger than cobbler \
                         mco agent timeout"
        try:
            _, errs = RpcCommandProcessorBase().execute_rpc_and_process_result(
                cb_api, nodes, "cobbler",
                cmd, cmd_args, timeout, 0)
        except RpcExecutionException as ex:
            raise CallbackExecutionException(*ex.args)
        if errs:
            str_errs = ', '.join([str(err) for err in reduce_errs(errs)])
            str_errs = "MCollective failure on action \"{0}\", diagnostic " \
                       "information: {1}".format(cmd, str_errs)
            raise CallbackExecutionException(str_errs)

    def _do_cobbler_remove_system(self, cb_api, nodes, system_name):
        self._do_cobbler_mco(cb_api, nodes, 'remove_system',
                             {'system': system_name})

    def _add_system_callback(self, cb_api, nodes, system_name, **kwargs):
        self._backup_anamon_logs(cb_api, nodes, kwargs['hostname'])

        command_args = {
            "system": system_name
        }
        command_args.update(kwargs)
        for k in command_args.keys():
            if not command_args[k]:
                del command_args[k]

        copy_keys = lambda orig_dict, keys: \
            dict([(k, v) for k, v in orig_dict.items() \
                  if k in keys])

        command_args_add = copy_keys(command_args, ["system", "profile"])

        edit_keys = ["system", "profile", "hostname", "kickstart"]
        command_args_edit = copy_keys(command_args, edit_keys)

        _log.trace.debug(
            '%s _add_system_callback '
            '%s, interfaces=%s, profile=%s, virt_data=%s)'
            % (cb_api.is_running(), system_name,
               command_args.get("interfaces"),
               command_args.get("profile"),
               command_args.get("virt_data")))

        virt_data = command_args.get("virt_data")

        all_ifaces = []
        interfaces = command_args.get("interfaces")
        for i in interfaces:
            iface = interfaces[i]
            iface['interface'] = i
            iface['system'] = system_name
            all_ifaces.append(iface)

        if interfaces:
            # following keys are per iface:
            # "ip_address", "mac_address", "dns_name"
            command_args_edit.update(all_ifaces.pop(0))

        if virt_data:
            command_args_edit.update(virt_data)

        self._do_cobbler_remove_system(cb_api, nodes, system_name)
        self._do_cobbler_mco(cb_api, nodes, 'add_system', command_args_add)
        self._do_cobbler_mco(cb_api, nodes, 'edit_system', command_args_edit)
        # add other iface data
        for iface in all_ifaces:
            self._do_cobbler_mco(cb_api, nodes, 'edit_system', iface)

        self._do_cobbler_mco(cb_api, nodes, 'sync', [])

    # Mocking time.time() directly is a nightmare..
    def _get_current_time(self):
        return int(time.time())

    def _wait_for_callback(self, callback_api, waiting_msg, callback,
                           *args, **kwargs):
        epoch = self._get_current_time()
        while not callback(*args, **kwargs):
            if not callback_api.is_running():
                raise PlanStoppedException(
                    "Plan execution has been stopped.")
            counter = self._get_current_time() - epoch
            if counter % 60 == 0:
                _log.trace.info(waiting_msg)
            if counter >= self._max_waiting_time_for_node:
                raise CallbackExecutionException(
                    "Node has not come up within {0} seconds".format(
                        self._max_waiting_time_for_node)
                )
            time.sleep(1.0)

    def _backup_anamon_logs(self, callback_api, nodes, hostname):
        cobbler_log_dir = '/var/log/cobbler'
        anamon_node_logs = os.path.join(cobbler_log_dir,
                                        'anamon/{0}/'.format(hostname))

        if os.path.isdir(anamon_node_logs) and os.listdir(anamon_node_logs):
            backup_dir = os.path.join(cobbler_log_dir, 'anamon.backup/')
            if not os.path.isdir(backup_dir):
                _log.trace.debug("Creating backup dir '{0}'".format(
                    backup_dir))
                self._do_cobbler_mco(callback_api, nodes,
                                     'create_directory',
                                     {'directory': backup_dir})

            _log.trace.debug("Backing up anamon logs for node")
            self._do_cobbler_mco(callback_api, nodes, 'backup_anamon',
                                 {'system': hostname})

            all_files = os.listdir(backup_dir)
            node_backup_dir = os.path.join(backup_dir, '{0}')
            backup_paths = [node_backup_dir.format(x) for x in all_files
                             if hostname in x]
            num_backups = 1
            if len(backup_paths) > num_backups:
                newest_file = max(backup_paths, key=os.path.getctime)
                backup_paths.remove(newest_file)

                for path in backup_paths:
                    _log.trace.debug("Number of backups greater than {0} "
                                     "removing '{1}'".format(num_backups,
                                                             path))
                    self._do_cobbler_mco(callback_api, nodes,
                                         'remove_directory',
                                         {'directory': path})
                    _log.trace.debug("Backup removed - {0}".format(path))

    def _install_node(self, callback_api, node_ip, hostname):
        self._wait_for_callback(
            callback_api,
            ("Waiting for node to come up: %s (%s)" % (hostname, node_ip)),
            self._check_node,
            hostname
        )
        _log.event.info("Node %s (%s) has come up.", hostname, node_ip)

    def _find_ip_for_node(self, node, network):

        _log.trace.debug("node net %s %s" % (node, network))
        for node_interface in node.network_interfaces:
            if node_interface.network_name:
                _log.trace.debug("Found net %s " % node_interface.network_name)
                if network.name == node_interface.network_name:
                    _log.trace.debug("Found ip %s " % node_interface.ipaddress)
                    return node_interface.ipaddress
        return None

    def _check_node(self, hostname):
        exit_code = run_rpc_application([hostname], ["ping"])
        # this should be checking only 0, but mcollective has a bug
        # https://tickets.puppetlabs.com/browse/MCO-199
        return exit_code in (0, 1)

    @staticmethod
    def _get_timezone():
        """
        @summary: Grabs the timezone from the timedatectl output on the MS
        """
        time_out = '/opt/ericsson/nms/litp/share/kickstart/timedatectl.out'
        timezone = None
        try:
            with open(time_out, 'r') as f:
                output = f.readlines()
            for line in output:
                if "Time zone:" in line:
                    timezone = line.split(":", 1)[-1]
                    timezone = timezone.strip(" ")
                    timezone = timezone.split(" ", 1)[0]
                    break
            if not timezone:
                raise IndexError("No timezone found in timedatectl output")
            return '--utc {0}'.format(timezone)
        except (IOError, IndexError) as err:
            timezone = "Europe/Dublin"
            _log.event.error("{0}. " \
                             "Using default timezone".format(err))
            return '--utc {0}'.format(timezone)

    def cb__write_snippet(self, callback_api, path, node_hostname, os_version,
                          boot_mode):
        """@summary write Kickstart snippet to the filesystem on the MS"""
        if os_version == "rhel6":
            config = self._get_lvm_kickstart_config_rhel6(
                callback_api, node_hostname)
        else:
            config = self._get_lvm_kickstart_config(
                callback_api, node_hostname, boot_mode)
        try:
            with os.fdopen(os.open(path,
                                   os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                                   0644), 'w') as f:
                f.writelines('\n'.join(config))
        except IOError:
            # The error-reporting mechanism only supports raising exceptions
            raise

    def _create_system_params(self, node, service, providers, plugin_context):

        boot_network = self._get_boot_network(plugin_context)
        boot_ipaddress = self._find_ip_for_node(node, boot_network)
        hostname = node.hostname
        ks_file = os.path.join(service.ksm_path,
                               hostname + '.ks')
        profile = node.os
        profile_name = "%s-%s" % (profile.name, profile.arch)
        _log.trace.debug('Using cobbler profile "%s" for node "%s"' % \
                         (profile_name, hostname))

        # gather params for new system
        system_params = {}
        system_params['node'] = node
        system_params['name'] = hostname
        system_params['kickstart'] = ks_file
        system_params['profile'] = profile_name
        system_params['mgmt_classes'] = "mgmt-nodes"

        # gather networking interface config
        device_name = self._get_dedicated_pxe_boot_only_nic(node)
        device_name = device_name or \
                      self._get_matching_nic_name(node, boot_network)
        _log.trace.debug('Device name "%s"' % device_name)
        macaddress = self._find_mac(node, device_name)
        device_name_values = {'mac_address': macaddress,
                              'ip_address': boot_ipaddress,
                              'dns_name': hostname}

        system_params['interfaces'] = {device_name: device_name_values}
        system_params['virt_data'] = {}
        # add additional params for libvirt / vm systems
        if node.system.item_type.item_type_id == 'libvirt-system':
            system_params['virt_data']['virt_path'] = node.system.path
            system_params['virt_data']['virt_file_size'] = \
                self.convert_to_gigabytes(self._get_system_disk(node).size)
            system_params['virt_data']['virt_ram'] = node.system.ram.strip('M')
            system_params['virt_data']['virt_cpus'] = node.system.cpus
            system_params['virt_data']['virt_type'] = 'qemu'
            system_params['interfaces'][device_name].update(
                {"virt_bridge": self._get_bridge(providers, node.system)})
            system_params['virt_data']['power_type'] = 'virsh'

        return system_params

    def _get_bridge_matching_nic(self, node, bridge_interface):
        """
        Looks for a network with the given name under node and returns the
        name of its associated NIC
        """
        br_ifaces = [nic for nic in node.network_interfaces if \
                     nic.item_type_id in \
                     ['eth', 'vlan', 'bond'] and \
                     hasattr(nic, 'bridge') and \
                     nic.bridge == bridge_interface.device_name]
        if not br_ifaces:
            return None
        br_iface = br_ifaces[0]
        if br_iface.item_type_id == 'eth':
            return br_iface
        elif br_iface.item_type_id == 'bond':
            slave = self._get_bond_eth_slaves(node, br_iface)[0]
            return slave
        if br_iface.item_type_id == 'vlan':
            dev_name = br_iface.device_name.split('.')[0]
            iface = self._get_interface_by_name(node, dev_name)
            if iface.item_type_id == 'eth':
                return iface
            if iface.item_type_id == 'bond':
                slave = self._get_bond_eth_slaves(node, iface)[0]
                return slave
        return None

    def _get_dedicated_pxe_boot_only_nic(self, node):
        """
        Looks for a NIC with pxe_boot_only set to true and get its device name.
        """
        # It's not needed to check whether the interface is is_initial
        # or is_for_removal, as it can not happen by validations.
        for interface in node.network_interfaces:
            if hasattr(interface, 'pxe_boot_only'):
                if interface.pxe_boot_only == 'true':
                    _log.trace.debug(
                        'pxe_boot_only device for {0} is {1}'.format(
                            node.hostname, interface.device_name))
                    return interface.device_name
        return None

    def _get_matching_nic_name(self, node, expected_network):
        """
        Looks for a network with the given name under node and returns the
        name of its associated NIC
        """
        if not node.network_interfaces:
            return
        for interface in node.network_interfaces:
            _log.trace.debug(
                'interface details "%s" "%s" "%s"',
                interface.device_name,
                interface.network_name,
                expected_network.name
            )
            if hasattr(interface, 'network_name') and \
                    interface.network_name == expected_network.name:
                if interface.item_type_id == 'bridge':
                    iface = self._get_bridge_matching_nic(node, interface)
                    return iface.device_name
                elif interface.item_type_id == 'vlan':
                    # split the device_name to get the real tagged interface
                    dev_name = interface.device_name.split('.')[0]
                    iface = self._get_interface_by_name(node, dev_name)
                    if iface.item_type_id == 'bond':
                        slave = self._get_bond_eth_slaves(node, iface)[0]
                        return slave.device_name
                    return iface.device_name
                elif interface.item_type_id == 'bond':
                    slave = self._get_bond_eth_slaves(node, interface)[0]
                    return slave.device_name
                return interface.device_name

    def _find_mac(self, node, interface):
        """ Given an interface name, returns the MAC address of the NIC within
        system that has that name.
        NOTE: for bond interfaces, if there is no MAC address associated the
        MAC address will be retrieved through the its eth slaves, in this
        case the first one.
        """
        for nic in node.network_interfaces:
            if nic.device_name == interface:
                _log.trace.debug("nic.item_type_id is %s " % nic.item_type_id)
                if nic.item_type_id == 'vlan':
                    # split the device_name to get the real tagged interface
                    dev_name = nic.device_name.split('.')[0]
                    # the nic variable is re-assigned to get the real tagged
                    # interface
                    nic = self._get_interface_by_name(node, dev_name)

                # here we test whether 'nic' is a bond, bridge  or eth (nic
                # could have been reassigned above in the 'vlan' condition)
                if nic.item_type_id == 'bond':
                    return self._get_bond_macaddress(node, nic)
                elif nic.item_type_id == 'bridge':
                    return self._get_bridge_macaddress(node, nic)
                elif nic.item_type_id == 'eth':
                    return nic.macaddress

    def _get_interfaces_by_type(self, node, type_name):
        """ Returns a list of interfaces by type_name.
        """
        return [item for item in node.query(type_name)
                if not item.is_removed() and not item.is_for_removal()]

    def _get_interface_by_name(self, node, name):
        """ Gets the interface object by name looking at all network
        interfaces.
        """
        interfaces = [i for i in node.network_interfaces
                      if i.device_name == name]
        return interfaces[0] if interfaces else None

    def _get_bond_eth_slaves(self, node, bond_interface):
        """ Returns a list of interfaces which are eth slaves for a given bond.
        The list is ordered by device_name ascending.
        """
        if bond_interface.item_type_id != 'bond':
            raise BootManagerException("The interface %s must be a bond type "
                                       "to get its slaves." % bond_interface)
        interfaces = self._get_interfaces_by_type(node, 'eth')
        name = bond_interface.device_name
        slaves = [e for e in interfaces if hasattr(e, 'master') and
                  e.master == name]
        slaves.sort(lambda a, b: cmp(a.device_name, b.device_name))
        _log.trace.debug("Found slaves: %s" % slaves)
        return slaves

    def _get_bond_macaddress(self, node, bond_interface):
        """ Gets the performing bond's MAC address. We assume that a bond
        interface has no MAC address associated so we get a single MAC address
        from the first item of the collection of the eth interfaces slaves.
        """
        slaves = self._get_bond_eth_slaves(node, bond_interface)
        return slaves[0].macaddress if slaves else None

    def _get_bridge_macaddress(self, node, bridge_interface):
        """ Gets the performing bridge's MAC address. We assume that a bridge
        interface has no MAC address associated so we get a single MAC address
        from the first item of the collection of the underlying interfaces.
        """
        _log.trace.debug("get_bridge MAC %s " % bridge_interface.device_name)

        br_ifaces = [nic for nic in node.network_interfaces if \
                     nic.item_type_id in \
                     ['eth', 'vlan', 'bond'] and \
                     hasattr(nic, 'bridge') and \
                     nic.bridge == bridge_interface.device_name]
        if not br_ifaces:
            return None
        br_iface = br_ifaces[0]
        if br_iface.item_type_id == 'eth':
            return br_iface.macaddress
        if br_iface.item_type_id == 'bond':
            return self._get_bond_macaddress(node, br_iface)
        if br_iface.item_type_id == 'vlan':
            dev_name = br_iface.device_name.split('.')[0]
            iface = self._get_interface_by_name(node, dev_name)
            if iface.item_type_id == 'eth':
                return iface.macaddress
            if iface.item_type_id == 'bond':
                return self._get_bond_macaddress(node, iface)

    def _get_bridge(self, providers, system):
        for provider in providers:
            for sys in provider.systems:
                if sys.system_name == system.system_name:
                    return provider.bridge
        return None

    def _get_cobbler_service(self, plugin_api_context):
        services = plugin_api_context.query("cobbler-service")
        if not services:
            _log.trace.debug("No cobbler service found")
            return None
        return services[0]

    def _get_providers(self, plugin_api_context):
        ms = plugin_api_context.query("ms")[0]
        return [ms.libvirt] if ms.libvirt else []

    def _nodes_in_the_deployment(self, plugin_api_context):
        return plugin_api_context.query("node", is_for_removal=False)

    @staticmethod
    def _validate_cobbler_service_exists(plugin_api_context):
        errors = []
        # need to do an explicit comparison because 'if service' won't work
        # due to the implementation of __len__ of QueryItem
        services = plugin_api_context.query("cobbler-service")
        if not services:
            msg = 'No cobbler service found'
            errors.append(ValidationError(error_message=msg))
        elif len(services) > 1:
            msg = 'More than one cobbler service found'
            errors.append(ValidationError(item_path=services[0].get_vpath(),
                                          error_message=msg))
        return errors

    def _validate_os_profile(self, plugin_api_context):

        errors = []

        os_profiles = plugin_api_context.query("os-profile")
        for os_profile in os_profiles:
            if os_profile.get_state() == "Updated":
                old_dict = os_profile.applied_properties
                new_dict = os_profile.properties
                diff = set(old_dict.iteritems()) - set(new_dict.iteritems())
                msg = ''
                for key, value in dict(diff).iteritems():
                    msg += 'Value of "%s" should be %s ' % (key, value)
                if msg:
                    errors.append(ValidationError(error_message=msg))

        return errors

    def _validate_boot_mode_on_cloud(self, nodes, cobbler_service):
        errors = []
        for node in nodes:
            if hasattr(cobbler_service, 'boot_mode') and 'uefi' == \
                    cobbler_service.boot_mode:
                for disk in node.system.disks:
                    if hasattr(disk, "uuid") and disk.uuid and not \
                            BootManagerPlugin._uuid_on_disk(disk):
                        msg = "UEFI boot_mode is not supported on a Cloud " \
                              "Environment"
                        errors.append(
                            ValidationError(error_message=msg,
                                            item_path=node.get_vpath()))
                        break
        return errors

    def _validate_br_in_libvirt(self, plugin_api_context, service):
        """
        For libvirt/vm systems, ensures that the system name in the provider
        (ms.libvirt) is the same as in the node system
        """
        errors = []
        # need a try/except in case there is no MS or that has been validated
        # already?
        providers = self._get_providers(plugin_api_context)
        for node in self._get_new_node_systems(plugin_api_context):
            if node.system.item_type.item_type_id == "libvirt-system":
                if not providers:
                    return [
                        ValidationError(
                            error_message="No libvirt-provider object "
                                          "found on ms",
                            item_path=service.get_vpath()
                        )
                    ]
                elif not self._get_bridge(providers, node.system):
                    msg = "providers {0} have no system with name {1}". \
                        format(providers, node.system)
                    errors.append(
                        ValidationError(
                            error_message=msg,
                            item_path=service.get_vpath()
                        )
                    )
        return errors

    @staticmethod
    def convert_to_gigabytes(size):
        """
        Converts a disk's size value to gigabytes equivalent to gibibytes
        (The default size value returned is '5')
        """

        pattern = r'^\s*(?P<size>[1-9][0-9]*)\s*(?P<unit>[MGT])\s*$'
        regexp = re.compile(pattern)
        match = regexp.search(size)

        if match:
            parts = match.groupdict()
            if parts:
                if 'size' in parts.keys():
                    value = int(parts['size'])

                    if 'unit' in parts.keys():
                        unit = parts['unit']
                        if unit == 'M':
                            value *= 0.001073741824
                        elif unit == 'G':
                            value *= 1.073741824
                        elif unit == 'T':
                            value *= 1073.741824
                        else:
                            return '5'
                        return str(int(math.ceil(value)))
                else:
                    return '5'
        else:
            return '5'
