# Script to remove linux multipather, install VxDMP and migrate all existing
# LVM volumes to DMP paths.

linux_device_mapper_rpms="device-mapper-multipath device-mapper-multipath-libs"
veritas_vxvm_rpms="VRTSperl VRTSvlic VRTSspt VRTSvxvm VRTSaslapm VRTSsfmh VRTSsfcpi61"
install_db="/etc/vx/reconfig.d/state.d/install-db"
array_info="/etc/vx/array.info"

VXDCTL=/opt/VRTS/bin/vxdctl
VXKEYLESS=/opt/VRTSvlic/bin/vxkeyless
KDUMP_CONFIG_FILE=/etc/kdump-adv-conf/initramfs.conf

function exit_on_error {
    echo $1 >&2
    if [ -f /tmp/vxdmp.log ] ; then
        cat /tmp/vxdmp.log
    fi
    exit $2
}

# Removing linux-device-mapper from node
yum remove -y ${linux_device_mapper_rpms} > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Can't remove linux multipather from node" 1
}
# Installing VxVM and VxDMP
# Workaround for VRTSvxvm 6.1 RPM. Adding libgcc.i686 to the installation list.
# The VRTSvxvm 6.1 RPM is dependent on 32bit libgcc regardless of platform.
yum install -y ${veritas_vxvm_rpms} libgcc.i686 > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Installation of VxVM failed" 2
}
# Setup SFHA license for Veritas
${VXKEYLESS} -q set SFHAENT > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Can't setup SFHA license for Veritas" 3
}
# Removing install-db file in order to start vxconfigd
if [ -f ${install_db} ] ; then
    rm -rf ${install_db}
fi
# Create array.info file to avoid console message about missing file.
# This file will be populated when we switch to enable mode
if [ ! -f {array_info} ] ; then
    touch ${array_info}
fi
# Start vxconfigd in disable mode
/sbin/vxconfigd -d -k > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Can't start vxconfigd deamon" 4
}
# Initialize vxdctl configuration deamon
${VXDCTL} init > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to initialize vxdctl" 5
}
${VXDCTL} initdmp > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to initialize vxdctl DMP" 6
}
# Discover VxVM disks
/sbin/vxdisk scandisks > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to discover VxVM disks" 7
}
# Scan LVM label disks
/sbin/lvmdiskscan > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to discover LVM disks" 8
}
# Backup orginal lvm.conf file before migration to native VxDMP
if [ -f /etc/lvm/lvm.conf ] ; then
   cp -f /etc/lvm/lvm.conf /etc/lvm/lvm.conf.org
fi

# (TORF-273666) RHEL 6.10 LVM to VxDMP migration pre-step fix. Remove VxDMP device files.
rm -f /dev/VxDMP*
rm -f /dev/dmpconfig
rm -f /dev/block/201*

# Migrate all LVM disks to VxDMP and rebuild initrd to include VxVM modules
vxdmpadm settune dmp_native_support=on > /tmp/vxdmp.log 2>&1
if [ $? -ne 0 -a $? -ne 215 ] ; then
    exit_on_error "ERROR: Failed migrate LVM disks to VxDMP multipather" $?
fi

# Update craskernel parameter to 256 MB in order to properly load
# kdump when linux kernel crashes. For details please see
# the Symantec TECH165726
if [ -f /boot/grub/grub.conf ] ; then
    grep -q 'crashkernel=auto' /boot/grub/grub.conf
    if (( $? == 0 )) ; then
        sed -i 's/crashkernel=auto/crashkernel=256M/g' /boot/grub/grub.conf
    else
        exit_on_error "ERROR: Failed to update crashkernel parameter in /boot/grub/grub.conf" 10
    fi
fi

# Workaround for Symantec case: 08259035 - "Kernel crash is not generating
# kernel dump after migrating root LVM to VxDMP"
# Include the /etc/kdump-adv-conf/initramfs.conf and set the lvmconf to no,
# this option will exclude the lvm.conf from dracut image and will not load
# the LVM filter. This will allow to mount the root disk over physical path
# during kernel crash when kdump image is used.
# see bug: http://jira-nam.lmera.ericsson.se/browse/LITPCDS-10634 for details
if [ ! -f ${KDUMP_CONFIG_FILE} ] ; then
    touch ${KDUMP_CONFIG_FILE}
    chmod u+rw ${KDUMP_CONFIG_FILE}
    echo "lvmconf=\"no\"" > ${KDUMP_CONFIG_FILE}
fi
# Remove vxdmp migration log file when all finished successfully.
if [ -f /tmp/vxdmp.log ] ; then
        rm -f /tmp/vxdmp.log
fi
