import subprocess

ERROR = 1  # generic or unspecified error
START_XINETD = "service xinetd start"
STOP_XINETD = "service xinetd stop"
STATUS_XINETD = "service xinetd status"


def register():
    return "/var/lib/cobbler/triggers/sync/pre/*"


def run(api, args, logger):
    """
    Method called by Cobbler as a pre-sync trigger.
    If systems are present and if the xinetd service is not running,
    it will start the service.
    If systems are not present it will stop the service
    :param api: Cobbler api used to check if systems are present
    :param args: Not used
    :param logger: Used for logging
    :return: 0 if actions were successful, non-zero otherwise.
    """
    # pylint: disable=W0613
    if not logger:
        logger = api.logger

    result = 0
    systems = api.systems().listing.keys()
    logger.debug('Pre-sync trigger with systems: ' + str(systems))

    if systems:
        if not is_xinetd_running(logger):
            logger.info("Systems listed, starting xinetd")
            result = subprocess_call(logger, START_XINETD)

            if result != 0:
                logger.error("Starting xinetd failed with return code: '{0}'"
                            .format(result))
    else:
        logger.info("No systems listed, stopping xinetd")
        result = subprocess_call(logger, STOP_XINETD)

        if result != 0:
            logger.error("Stopping xinetd failed with return code: '{0}'"
                         .format(result))

    return result


def subprocess_call(logger, cmd):
    """
    Executes the command passed as a new process
    :param logger: Used for logging
    :param cmd: The command to execute
    :return: The result of command execution, 0 if successful,
    non-zero otherwise.
    """
    logger.info("Running command : %s" % cmd)

    try:
        sp = subprocess.Popen(cmd, shell=True, stdin=None,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              close_fds=True)
    except OSError as error:
        logger.info("Exception occurred executing subprocess for command "
                    "{0}. Exception info: {1}".format(cmd, str(error)))
        return ERROR

    (out, err) = sp.communicate()
    rc = sp.returncode

    if rc != 0:
        logger.info("Received on stdout: %s" % out.strip())
        logger.debug("Received on stderr: %s" % err.strip())

    return rc


def is_xinetd_running(logger):
    """
    Boolean method to determine if the xinetd service is running.
    :param logger: Used for logging the status of the xinetd service
    :return: True if the xinetd service is running, False otherwise.
    """
    xinetd_running = False

    result = subprocess_call(logger, STATUS_XINETD)
    if result == 0:
        xinetd_running = True
        logger.info("xinetd service is already running.")
    else:
        logger.info("xinetd service is not running. Status check returned " \
                "code: '{0}'".format(result))

    return xinetd_running
