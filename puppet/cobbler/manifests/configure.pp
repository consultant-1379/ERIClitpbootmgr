define cobbler::configure(
                          $server,
                          $puppet_auto_setup='1',
                          $sign_puppet_certs_automatically='1',
                          $remove_old_puppet_certs_automatically='1',
                          $manage_dhcp='1',
                          $manage_dns='0',
                          $authentication='authn_testing',
                          $rsync_disabled='no',
                          $networks=[{}],
                          $boot_mode='bios',
                          $distro='',
                          ) {

  include litpweb::params
  include litp::httpd

  $packages = [ 'EXTRlitpcobbler_CXP9030601', 'xinetd' ]

  $services = [ 'cobblerd' ]

  package{ $packages: ensure => installed }

  service { $services :
    ensure => running,
    enable => true,
  }

  service { 'xinetd' :
    enable => false,
  }

  file { 'rsync':
    ensure  => file,
    path    => '/etc/xinetd.d/rsync',
    mode    => '0755',
    owner   => root,
    group   => root,
    require => Package['EXTRlitpcobbler_CXP9030601'],
    content => template('cobbler/rsync.erb'),
    notify  => Service['cobblerd'],
  }

  file { 'settings':
    ensure  => file,
    path    => '/etc/cobbler/settings',
    mode    => '0664',
    owner   => root,
    group   => root,
    require => Package['EXTRlitpcobbler_CXP9030601'],
    content => template('cobbler/settings.erb'),
    notify  => Service['cobblerd'],
  }

#  file { 'users.digest':
#    ensure  => file,
#    path    => '/etc/cobbler/users.digest',
#    mode    => '0664',
#    owner   => root,
#    group   => root,
#    require => Package['cobbler'],
#    content => 'cobbler:Cobbler:8e761a1854cc1c0a27f3f9c86036140e',
#    notify  => Service['cobblerd'],
#  }

  file { 'modules':
    ensure  => file,
    path    => '/etc/cobbler/modules.conf',
    mode    => '0755',
    owner   => root,
    group   => root,
    require => Package['EXTRlitpcobbler_CXP9030601'],
    content => template('cobbler/modules.erb'),
    notify  => Service['cobblerd'],
  }

  if $boot_mode == 'uefi' {

    $loaders_distro_dir = "/var/lib/cobbler/loaders/${distro}/"

    file { 'grubefi':
      ensure  => file,
      path    => "${loaders_distro_dir}/grubx64.efi",
      mode    => '0744',
      owner   => root,
      group   => root,
      require => [Package['EXTRlitpcobbler_CXP9030601'], File[$loaders_distro_dir]],
      source  => ['/var/tmp/litpd/grubx64.efi', '/boot/efi/EFI/redhat/grubx64.efi'],
      notify  => Service['cobblerd'],
    }

    file { $loaders_distro_dir:
      ensure => directory,
      mode   => '0755',
      owner  => 'root',
      group  => 'root',
    }

    file { 'grubsystem':
      ensure  => file,
      path    => '/etc/cobbler/pxe/grubsystem.template',
      mode    => '0644',
      owner   => root,
      group   => root,
      require => Package['EXTRlitpcobbler_CXP9030601'],
      content => template('cobbler/grubsystem.template.erb'),
      notify  => Service['cobblerd'],
    }

    file { 'uefi-boot':
      ensure  => file,
      path    => '/var/lib/cobbler/triggers/sync/post/uefi-boot',
      mode    => '0744',
      source  => 'puppet:///modules/cobbler/uefi-boot',
      require => Package['EXTRlitpcobbler_CXP9030601'],
      notify  => Service['cobblerd'],
    }
  }

  file { 'dhcp':
    ensure  => file,
    path    => '/etc/cobbler/dhcp.template',
    mode    => '0755',
    owner   => root,
    group   => root,
    require => [Package['EXTRlitpcobbler_CXP9030601'], Service['cobblerd']],
    content => template('cobbler/dhcp.template.erb'),
    notify  => Exec['cobblersync'],
  }

  exec { 'cobblersync':
    command     => 'cobbler sync',
    path        => '/usr/bin/',
    subscribe   => File['settings'],
    require     => [File['settings', 'dhcp', 'modules', 'rsync'],  Service['cobblerd']],
    refreshonly => true,
  }

  exec { 'timezone':
    command => "timedatectl | grep 'Time zone' | sed -e 's/^[[:space:]]*//' > /etc/sysconfig/clock",
    unless  => 'test -f /etc/sysconfig/clock',
    path    => ['/usr/bin', '/bin'],
  }
}

