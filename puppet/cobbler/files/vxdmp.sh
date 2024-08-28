# Script to remove linux multipather, install VxDMP and migrate all existing
# LVM volumes to DMP paths.

linux_device_mapper_rpms="device-mapper-multipath device-mapper-multipath-libs"
veritas_vxvm_rpms="VRTSperl VRTSvlic VRTSspt VRTSvxvm VRTSaslapm VRTSsfmh VRTSsfcpi"
install_db="/etc/vx/reconfig.d/state.d/install-db"
array_info="/etc/vx/array.info"

VXDCTL=/opt/VRTS/bin/vxdctl
VXKEYLESS=/opt/VRTS/bin/vxkeyless
KDUMP_CONFIG_FILE=/etc/kdump-adv-conf/initramfs.conf
VRPORT=/opt/VRTS/bin/vrport

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

# RHEL 7: Workaround - install and start veki first
yum install -y VRTSveki > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Installation of VRTSveki failed" 2
}

/etc/init.d/veki start > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: /etc/init.d/veki failed to start" 3
}

if [ `ls -l /lib/modules 2>/dev/null | wc -l` -gt 2 ] ; then
    mkdir -p /lib/modules/`rpm -q --queryformat "%{VERSION}-%{RELEASE}.%{ARCH}" kernel`/veritas/veki/
    cp -P /lib/modules/`uname -r`/veritas/veki/veki.ko /lib/modules/`rpm -q --queryformat "%{VERSION}-%{RELEASE}.%{ARCH}" kernel`/veritas/veki/
fi

# Installing VxVM and VxDMP
# Workaround for VRTSvxvm 6.1 RPM. Adding libgcc.i686 to the installation list.
# The VRTSvxvm 6.1 RPM is dependent on 32bit libgcc regardless of platform.
yum install -y ${veritas_vxvm_rpms} libgcc.i686 > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Installation of VxVM failed" 4
}
# Setup SFHA license for Veritas
${VXKEYLESS} set -q ENTERPRISE > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Can't setup SFHA license for Veritas" 5
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
    exit_on_error "ERROR: Can't start vxconfigd deamon" 6
}
# Initialize vxdctl configuration deamon
${VXDCTL} init > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to initialize vxdctl" 7
}
${VXDCTL} initdmp > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to initialize vxdctl DMP" 8
}

# (TORF-489029) Start vxrsyncd on non-clashing port i.e. not 8989
${VRPORT} vxrsyncd 8999 > /tmp/vxdmp.log 2>&1 || {
     exit_on_error "ERROR: Failed to change vxrsyncd port" 9
}
# Discover VxVM disks
/sbin/vxdisk scandisks > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to discover VxVM disks" 10
}
# Scan LVM label disks
/sbin/lvmdiskscan > /tmp/vxdmp.log 2>&1 || {
    exit_on_error "ERROR: Failed to discover LVM disks" 11
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
if [ -f /boot/grub2/grub.cfg ] ; then
    grep -q 'crashkernel=auto' /boot/grub2/grub.cfg
    if (( $? == 0 )) ; then
        sed -i 's/crashkernel=auto/crashkernel=256M/g' /boot/grub2/grub.cfg
    else
        exit_on_error "ERROR: Failed to update crashkernel parameter in /boot/grub2/grub.cfg" 12
    fi
fi

# Remove vxdmp migration log file when all finished successfully.
if [ -f /tmp/vxdmp.log ] ; then
        rm -f /tmp/vxdmp.log
fi
