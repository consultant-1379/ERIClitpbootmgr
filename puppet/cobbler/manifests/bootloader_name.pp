define cobbler::bootloader_name($path='/var/lib/cobbler/snippets',
                          $boot_disk_uuid="",
                          $boot_disk_name="",
                          $snippet_name="",
                          $os_version="",
                          ) {
  if $os_version == 'rhel6' {
    $os_version_dir = 'rhel6/'
  } else {
    $os_version_dir = ''
  }

  file { "${path}/${snippet_name}":
    ensure  => file,
    path    => "${path}/${snippet_name}",
    mode    => '0644',
    owner   => root,
    group   => root,
    require => [Package['EXTRlitpcobbler_CXP9030601'],File['dhcp']],
    content => template("cobbler/${os_version_dir}bootloader_name.erb"),
  }
}
