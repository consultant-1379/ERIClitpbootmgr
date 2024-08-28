define cobbler::kickstart($selinux_mode='enforcing',
                          $path='/var/lib/cobbler/kickstarts',
                          $ksname='litp.ks',
                          $snippet_path='/var/lib/cobbler/snippets',
                          $timezone='--utc Europe/Dublin',
                          $keyboard='uk',
                          $partitioninfo="",
                          $cluster_type="",
                          $ms_hostname="ms1",
                          $os_version="",
                          $os_reinstall='false',
                          $boot_mode="bios",
                          $boot_disk="",
                          $add_lvm_conf='false',
                          $lvm_uuids=[],
                          $openstack_env='false',
                          ) {
  if $os_version == 'rhel6' {
      $content_dir = 'rhel6/'
      $source_dir = 'rhel6/'
  } elsif $os_reinstall == 'true' and $cluster_type == 'sfha' {
      $content_dir = ''
      $source_dir = 'rhel7_sfha/'
  } else {
      $content_dir = ''
      $source_dir = ''
  }

  file { "${path}/${ksname}":
    ensure  => file,
    path    => "${path}/${ksname}",
    mode    => '0755',
    owner   => root,
    group   => root,
    require => [File['dhcp'], Package['EXTRlitpcobbler_CXP9030601']],
    content => template("cobbler/${content_dir}kickstart.erb"),
  }

  if $cluster_type == "sfha" {
    if $os_version != 'rhel6' {
      file { "${snippet_path}/${ksname}.vxdmp.snippet":
        ensure  => file,
        path    => "${snippet_path}/${ksname}.vxdmp.snippet",
        mode    => '0644',
        content => template("cobbler/vxdmp.erb"),
        require => Package['EXTRlitpcobbler_CXP9030601'],
      }
    }
    else {
      file { "${snippet_path}/${ksname}.vxdmp.snippet":
        ensure  => file,
        path    => "${snippet_path}/${ksname}.vxdmp.snippet",
        mode    => '0644',
        source  => "puppet:///modules/cobbler/${source_dir}vxdmp.sh",
        require => Package['EXTRlitpcobbler_CXP9030601'],
      }
    }
  }
}
