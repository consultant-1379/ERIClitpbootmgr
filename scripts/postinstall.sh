#!/bin/sh

LITP_ACTION=$1
LITP_UPGRADE=2
SYSTEMCTL=/usr/bin/systemctl

setsebool -P httpd_can_network_connect_cobbler on

semodule -i /opt/ericsson/nms/litp/etc/selinux/cobblerd.pp

#Outputs timezone and keyboard data for use during create_plan
mkdir -p /opt/ericsson/nms/litp/share/kickstart/

/usr/bin/localectl > /opt/ericsson/nms/litp/share/kickstart/localectl.out
/usr/bin/timedatectl > /opt/ericsson/nms/litp/share/kickstart/timedatectl.out

semanage fcontext -l | grep -e "/opt/ericsson/nms/litp/share/kickstart(/.*)?" > /dev/null
semng_label_rc=$?
if [ "${semng_label_rc}" -ne "0" ]; then
    semanage fcontext -a -e /opt/ericsson/nms/litp/share '/opt/ericsson/nms/litp/share/kickstart(/.*)?'
fi

restorecon -v /opt/ericsson/nms/litp/share/kickstart/

sed -i -e '/postrotate/,+4d' /etc/logrotate.d/cobblerd &&  sed -i '/weekly/a\   copytruncate' /etc/logrotate.d/cobblerd

if [ "${LITP_ACTION}" -ge "${LITP_UPGRADE}" ]; then
    ${SYSTEMCTL} status cobblerd.service && ${SYSTEMCTL} try-restart cobblerd.service || ${SYSTEMCTL} start cobblerd.service
fi

exit 0
