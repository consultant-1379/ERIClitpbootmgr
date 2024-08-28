define cobbler::multipath(
                        $mpaths = [{}],
                        $path='/var/lib/cobbler/snippets',
                        $snippet_name = '',
                        $os_version=""
                        ) {

  if $os_version == 'rhel6' {
    $os_version_dir = 'rhel6/'
  } else {
    $os_version_dir = ''
  }

   file { "${path}/${snippet_name}":
      mode    => '0755',
      owner   => root,
      group   => root,
      require => [Package['EXTRlitpcobbler_CXP9030601'], File['dhcp']],
      path    => "${path}/${snippet_name}",
      content => template("cobbler/etc/multipath.conf.erb", "cobbler/etc/${os_version_dir}multipaths.erb"),
   }
}
