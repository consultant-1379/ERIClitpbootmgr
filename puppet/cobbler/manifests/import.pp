# cobbler::profile
# imports a cobbler profile
class cobbler::import ($name, $path) {

  file { 'import.sh':
    ensure => file,
    path   => '/opt/ericsson/nms/litp/litp_boot_cobbler/import.sh',
    source => 'puppet:///modules/profile-import/import.sh',
    owner  => root,
    group  => root,
    mode   => '0744',
  }

  exec { 'base-profile-import':
    cwd     => '/opt/ericsson/nms/litp/litp_boot_cobbler',
    path    => '/bin/:/usr/sbin:/sbin/:/usr/bin/',
    command => "/opt/ericsson/nms/litp/litp_boot_cobbler/import.sh > /root/profile_${name}_import.log",
    creates => "/var/www/cobbler/images/${name}",
    require => [Service['cobblerd'],File['dhcp']],
    notify  => Exec['profile_import_feedback'],
  }

  exec { 'profile_import_feedback':
    command     => "/usr/bin/curl http://mws-1:9999/LOG/inventory/site1/node/$::hostname/profile-import/feedback",
    refreshonly => true,
  }
}
