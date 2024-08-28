from triggers.cobbler import sync_pre_trigger
from triggers.cobbler import install_pre_pxe

import unittest
import subprocess

from mock import Mock, MagicMock, patch, call

class CobblerPreSyncTriggerTest(unittest.TestCase):

    def setUp(self):
        self.test_class = sync_pre_trigger
        self.start_xinetd_cmd = "service xinetd start"
        self.stop_xinetd_cmd = "service xinetd stop"
        self.status_xinetd_cmd = "service xinetd status"
        self.stdin = None
        self.close_fds = True
        self.shell = True
        self.logger = MagicMock()
        self.api = MagicMock()
        self.api.logger.return_value = self.logger
        self.logger.info = MagicMock()
        self.logger.error = MagicMock()
        self.logger.debug = MagicMock()
        self.mocksystems = MagicMock()
        self.api.systems.return_value = self.mocksystems
        self.system_exist_start_message = 'Systems listed, starting xinetd'
        self.system_empty_stop_message = 'No systems listed, stopping xinetd'
        self.run_command_start_message = "Running command : service xinetd start"
        self.print_systems_message = 'Pre-sync trigger with systems: '

    def tearDown(self):
        reload(sync_pre_trigger)

    @patch('subprocess.Popen')
    def test_subprocess_call_start_success(self, mock_popen):

        mock_process = Mock()
        mock_process.communicate.return_value = (
            'Starting xinetd:   [  OK  ] ', '')
        mock_process.returncode = 0

        mock_popen.return_value = mock_process

        self.assertEqual(mock_process.returncode,
                         self.test_class.subprocess_call(self.logger,
                                                         self.start_xinetd_cmd))
        self.assertEquals(1, mock_process.communicate.call_count)

        mock_popen.assert_called_once_with(self.start_xinetd_cmd, shell=True,
                                           stdin=None, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           close_fds =True)
        calls = [call(self.run_command_start_message)]
        self.logger.info.assert_has_calls(calls)

    @patch('subprocess.Popen')
    def test_subprocess_call_start_OS_Error(self, mock_popen):
        mock_popen.side_effect = OSError("OSError")

        self.assertEqual(1, self.test_class.subprocess_call(self.logger,
                                                         self.start_xinetd_cmd))
        mock_popen.assert_called_once_with(self.start_xinetd_cmd, shell=True,
                                           stdin=None, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           close_fds=True)

        calls = [call(self.run_command_start_message),
                 call("Exception occurred executing subprocess for command "\
                    "service xinetd start. Exception info: OSError")]
        self.logger.info.assert_has_calls(calls)

    @patch('subprocess.Popen')
    def test_subprocess_call_cmd_fail_result(self, mock_popen):
        mock_process = Mock()
        mock_process.communicate.return_value = (
            'Starting xinetd:   [  NOK  ] ', 'Error starting xinetd...\n')
        mock_process.returncode = 6
        mock_popen.return_value = mock_process

        self.assertEqual(mock_process.returncode,
                         self.test_class.subprocess_call(self.logger,
                                                         self.start_xinetd_cmd))
        mock_popen.assert_called_once_with(self.start_xinetd_cmd, shell=True,
                                           stdin=None, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           close_fds=True)

        calls = [call(self.run_command_start_message),
                 call("Received on stdout: Starting xinetd:   [  NOK  ]")]
        self.logger.info.assert_has_calls(calls)
        self.logger.debug.assert_called_once_with("Received on stderr: " \
                                                  "Error starting xinetd...")

    @patch('triggers.cobbler.sync_pre_trigger.subprocess_call')
    def test_is_xinetd_running_running(self, mock_subprocess_call):
        mock_subprocess_call.return_value = 0
        self.assertEqual(True, self.test_class.is_xinetd_running(self.logger))
        mock_subprocess_call.assert_called_once_with(self.logger,
                                                     self.status_xinetd_cmd)
        self.logger.info.assert_called_once_with("xinetd service is already running.")

    @patch('triggers.cobbler.sync_pre_trigger.subprocess_call')
    def test_is_xinetd_running_not_running(self, mock_subprocess_call):
        mock_subprocess_call.return_value = 3
        self.assertEqual(False, self.test_class.is_xinetd_running(self.logger))
        mock_subprocess_call.assert_called_once_with(self.logger,
                                                     self.status_xinetd_cmd)
        self.logger.info.assert_called_once_with("xinetd service is not running. " \
                                                 "Status check returned code: '{0}'"
                                                 .format(mock_subprocess_call.return_value))

    @patch('triggers.cobbler.sync_pre_trigger.subprocess_call')
    @patch('triggers.cobbler.sync_pre_trigger.is_xinetd_running')
    def test_run_with_systems_success(self, mock_is_xinetd_running,
                                      mock_subprocess_call):

        self.mocksystems.listing = {"node1": MagicMock(), "node2": MagicMock()}
        mock_is_xinetd_running.return_value = False
        mock_subprocess_call.return_value = 0

        self.assertEqual(0, self.test_class.run(self.api, None, None))
        mock_subprocess_call.assert_called_once_with(self.api.logger,
                                                     self.start_xinetd_cmd)
        self.api.logger.debug.assert_called_once_with(self.print_systems_message
                                                      + str(self.mocksystems.listing.keys()))
        self.api.logger.info.assert_called_once_with(self.system_exist_start_message)

    @patch('triggers.cobbler.sync_pre_trigger.subprocess_call')
    def test_run_with_nosystems_success(self, mock_subprocess_call):
        self.mocksystems.listing = {}
        mock_subprocess_call.return_value = 0

        self.assertEqual(0, self.test_class.run(self.api, None, self.logger))
        mock_subprocess_call.assert_called_once_with(self.logger,
                                                     self.stop_xinetd_cmd)
        self.logger.debug.assert_called_once_with(self.print_systems_message +
                                                  str(self.mocksystems.listing.keys()))
        self.logger.info.assert_called_once_with(self.system_empty_stop_message)

    @patch('triggers.cobbler.sync_pre_trigger.subprocess_call')
    @patch('triggers.cobbler.sync_pre_trigger.is_xinetd_running')
    def test_run_with_systems_fail(self, mock_is_xinetd_running,
                                   mock_subprocess_call):

        self.mocksystems.listing = {"node1": MagicMock(), "node2": MagicMock()}
        mock_is_xinetd_running.return_value = False
        mock_subprocess_call.return_value = 6

        self.assertEqual(mock_subprocess_call.return_value,
                         self.test_class.run(self.api, None, self.logger))
        mock_subprocess_call.assert_called_once_with(self.logger,
                                                     self.start_xinetd_cmd)
        self.logger.debug.assert_called_once_with(self.print_systems_message +
                                                  str(self.mocksystems.listing.keys()))
        self.logger.info.assert_called_once_with(self.system_exist_start_message)
        self.logger.error.assert_called_once_with("Starting xinetd failed "
                                                  "with return code: '{0}'"
                                                  .format(str(mock_subprocess_call.return_value)))

    @patch('triggers.cobbler.sync_pre_trigger.subprocess_call')
    def test_run_with_nosystems_fail(self, mock_subprocess_call):
        self.mocksystems.listing = {}
        mock_subprocess_call.return_value = 1

        self.assertEqual(mock_subprocess_call.return_value,
                         self.test_class.run(self.api, None, self.logger))
        mock_subprocess_call.assert_called_once_with(self.logger,
                                                     self.stop_xinetd_cmd)
        self.logger.debug.assert_called_once_with(self.print_systems_message +
                                                  str(self.mocksystems.listing.keys()))
        self.logger.info.assert_called_once_with(self.system_empty_stop_message)
        self.logger.error.assert_called_once_with(
            "Stopping xinetd failed with return code: '{0}'"
            .format(str(mock_subprocess_call.return_value)))

    @patch('triggers.cobbler.sync_pre_trigger.subprocess_call')
    @patch('triggers.cobbler.sync_pre_trigger.is_xinetd_running')
    def test_run_with_systems_success_xinetd_already_running(self,
                                                             mock_is_xinetd_running,
                                                             mock_subprocess_call):
        self.mocksystems.listing = {"node1": MagicMock(), "node2": MagicMock()}
        mock_is_xinetd_running.return_value = True

        self.assertEqual(0, self.test_class.run(self.api, None, self.logger))

        mock_subprocess_call.assert_has_calls([])
        self.logger.debug.assert_called_once_with(self.print_systems_message
                                                      + str(self.mocksystems.listing.keys()))

    def test_register(self):
        expected = "/var/lib/cobbler/triggers/sync/pre/*"
        self.assertEqual(expected, self.test_class.register())


class CobblerInstallPrePxeTriggerTest(unittest.TestCase):
    def setUp(self):
        self.test_class = install_pre_pxe

    def tearDown(self):
        reload(install_pre_pxe)

    def test_run(self):

        args = ["system", "node1"]
        system = MagicMock()
        system.set_comment.return_value = 0
        api = MagicMock()
        api.find_system.return_value = system

        self.assertEqual(0, self.test_class.run(api, args, None))
        system.set_comment.assert_called_once_with("PXE_BOOTED")

    def test_register(self):
        expected = "/var/lib/cobbler/triggers/install/pre/*"
        self.assertEqual(expected, self.test_class.register())
