
class task_ms1__cobbler_3a_3abootloader__node1(){
    cobbler::bootloader { "node1":
        boot_disk_uuid => "0x5000c50035ca73fe",
        os_version => "rhel7",
shared_uuids => [

        ]
,
        snippet_name => "node1.ks.bootloader.snippet"
    }
}

class task_ms1__cobbler_3a_3abootloader__node2(){
    cobbler::bootloader { "node2":
        boot_disk_uuid => "0x5000c50035ca73ff",
        os_version => "rhel7",
shared_uuids => [

        ]
,
        snippet_name => "node2.ks.bootloader.snippet"
    }
}

class task_ms1__cobbler_3a_3aconfigure__bootservice__cfg(){
    cobbler::configure { "bootservice_cfg":
        authentication => "authn_configfile",
        boot_mode => "bios",
        distro => "node-iso-x86_64",
        manage_dhcp => "1",
        manage_dns => "0",
networks => [
{
        subnet => "10.4.23.0",
        netmask => "255.255.255.0"
        }
        ]
,
        puppet_auto_setup => "1",
        remove_old_puppet_certs_automatically => "1",
        rsync_disabled => "no",
        server => "10.4.23.50",
        sign_puppet_certs_automatically => "1"
    }
}

class task_ms1__cobbler_3a_3akickstart__node1(){
    cobbler::kickstart { "node1":
        add_lvm_conf => "false",
        boot_mode => "bios",
        cluster_type => "",
        keyboard => "uk",
        ksname => "node1.ks",
lvm_uuids => [

        ]
,
        ms_hostname => "ms1",
        openstack_env => "false",
        os_reinstall => "false",
        os_version => "rhel7",
        partitioninfo => "%include /tmp/partitioninfo",
        path => "/var/lib/cobbler/kickstarts",
        selinux_mode => "enforcing",
        timezone => "--utc Europe/Dublin"
    }
}

class task_ms1__cobbler_3a_3akickstart__node2(){
    cobbler::kickstart { "node2":
        add_lvm_conf => "false",
        boot_mode => "bios",
        cluster_type => "",
        keyboard => "uk",
        ksname => "node2.ks",
lvm_uuids => [

        ]
,
        ms_hostname => "ms1",
        openstack_env => "false",
        os_reinstall => "false",
        os_version => "rhel7",
        partitioninfo => "%include /tmp/partitioninfo",
        path => "/var/lib/cobbler/kickstarts",
        selinux_mode => "enforcing",
        timezone => "--utc Europe/Dublin"
    }
}

class task_ms1__cobbler_3a_3audev__network__node1(){
    cobbler::udev_network { "node1":
network_cards => [
{
        mac => "08:00:27:5b:c1:3f",
        dev => "eth0"
        }
        ]
,
        path => "/var/lib/cobbler/snippets",
        snippet_name => "node1.ks.udev_network.snippet"
    }
}

class task_ms1__cobbler_3a_3audev__network__node2(){
    cobbler::udev_network { "node2":
network_cards => [
{
        mac => "08:00:27:5b:c1:3a",
        dev => "eth0"
        }
        ]
,
        path => "/var/lib/cobbler/snippets",
        snippet_name => "node2.ks.udev_network.snippet"
    }
}

class task_ms1__cobblerdata_3a_3aadd__profile__node_2diso_2dx86__64(){
    cobblerdata::add_profile { "node-iso-x86_64":
        distro => "node-iso-x86_64",
        kickstart => "/var/lib/cobbler/kickstarts/default.ks",
kopts => {
        ksdevice => "",
        'inst.repo' => "http://@@http_server@@/7/os/x86_64/",
        'net.ifnames' => "0"
        },
ks_opts_post => {
        console => "ttyS0,115200"
        },
repos => [

        ]

    }
}

class task_ms1__cobblerdata_3a_3aadd__profile__sample_2dprofile_2dx86__64(){
    cobblerdata::add_profile { "sample-profile-x86_64":
        distro => "sample-profile-x86_64",
        kickstart => "/var/lib/cobbler/kickstarts/default.ks",
kopts => {
        ksdevice => "",
        'inst.repo' => "http://@@http_server@@/7/os/x86_64/",
        'net.ifnames' => "0"
        },
ks_opts_post => {
        console => "ttyS0,115200"
        },
repos => [

        ]

    }
}

class task_ms1__cobblerdata_3a_3aimport__distro__node_2diso_2dx86__64(){
    cobblerdata::import_distro { "node-iso-x86_64":
        arch => "x86_64",
        breed => "redhat",
        os_version => "rhel7",
        path => "/var/www/html/7/os/x86_64/",
        url_path => "7/os/x86_64/"
    }
}

class task_ms1__cobblerdata_3a_3aimport__distro__sample_2dprofile_2dx86__64(){
    cobblerdata::import_distro { "sample-profile-x86_64":
        arch => "x86_64",
        breed => "redhat",
        os_version => "rhel7",
        path => "/var/www/html/7/os/x86_64/",
        url_path => "7/os/x86_64/"
    }
}


node "ms1" {

    class {'litp::ms_node':}


    class {'task_ms1__cobbler_3a_3abootloader__node1':
    }


    class {'task_ms1__cobbler_3a_3abootloader__node2':
    }


    class {'task_ms1__cobbler_3a_3aconfigure__bootservice__cfg':
    }


    class {'task_ms1__cobbler_3a_3akickstart__node1':
    }


    class {'task_ms1__cobbler_3a_3akickstart__node2':
    }


    class {'task_ms1__cobbler_3a_3audev__network__node1':
    }


    class {'task_ms1__cobbler_3a_3audev__network__node2':
    }


    class {'task_ms1__cobblerdata_3a_3aadd__profile__node_2diso_2dx86__64':
        require => [Class["task_ms1__cobblerdata_3a_3aimport__distro__node_2diso_2dx86__64"]]
    }


    class {'task_ms1__cobblerdata_3a_3aadd__profile__sample_2dprofile_2dx86__64':
        require => [Class["task_ms1__cobblerdata_3a_3aimport__distro__sample_2dprofile_2dx86__64"]]
    }


    class {'task_ms1__cobblerdata_3a_3aimport__distro__node_2diso_2dx86__64':
    }


    class {'task_ms1__cobblerdata_3a_3aimport__distro__sample_2dprofile_2dx86__64':
    }


}
