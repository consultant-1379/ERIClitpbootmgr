define cobbler::udev_network(
                        $network_cards = [{}],
                        $path='/var/lib/cobbler/snippets',
                        $snippet_name = ''
                        ) {

   file { "${path}/${snippet_name}":
      mode    => '0644',
      owner   => root,
      group   => root,
      require => [Package['EXTRlitpcobbler_CXP9030601'],File['dhcp']],
      path    => "${path}/${snippet_name}",
      content => template("cobbler/udev_network.erb"),
   }
}
