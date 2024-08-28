# Class: cobbler
#
# This class manages Cobbler
# https://fedorahosted.org/cobbler/
#
# Parameters:
#
#   - $service_name [type: string]
#     Name of the cobbler service, defaults to 'cobblerd'.
#
#   - $package_name [type: string]
#     Name of the installation package, defaults to 'cobbler'
#
#   - $package_ensure [type: string]
#     Defaults to 'present', buy any version can be set
#
#   - $distro_path [type: string]
#     Defines the location on disk where distro files will be
#     stored. Contents of the ISO images will be copied over
#     in these directories, and also kickstart files will be
#     stored. Defaults to '/distro'
#
#   - $manage_dhcp [type: bool]
#     Wether or not to manage ISC DHCP.
#
#   - $dhcp_dynamic_range [type: string]
#     Range for DHCP server
#
#   - $manage_dns [type: string]
#     Wether or not to manage DNS
#
#   - $dns_option [type: string]
#     Which DNS deamon to manage - Bind or dnsmasq. If dnsmasq,
#     then dnsmasq has to be used for DHCP too.
#
#   - $manage_tftpd [type: bool]
#     Wether or not to manage TFTP daemon.
#
#   - $tftpd_option [type:string]
#     Which TFTP daemon to use.
#
#   - $server_ip [type: string]
#     IP address of a server.
#
#   - $next_server_ip [type: string]
#     Next Server in cobbler config.
#
#   - $nameserversa [type: array]
#     Nameservers for kickstart files to put in resolv.conf upon
#     installation.
#
#   - $dhcp_interfaces [type: array]
#     Interface for DHCP to listen on.
#
#   - $dhcp_subnets [type: array]
#     If you use *DHCP relay* on your network, then $dhcp_interfaces
#     won't suffice. $dhcp_subnets have to be defined, otherwise,
#     DHCP won't offer address to a machine in a network that's
#     not directly available on the DHCP machine itself.
#
#   - $defaultrootpw [type: string]
#     Hash of root password for kickstart files.
#
#   - $apache_service [type: string]
#     Name of the apache service.
#
#   - $allow_access [type: string]
#     For what IP addresses/hosts will access to cobbler_api be granted.
#     Default is for server_ip, ::ipaddress and localhost
#
#   - $purge_distro  [type: bool]
#   - $purge_repo    [type: bool]
#   - $purge_profile [type: bool]
#   - $purge_system  [type: bool]
#     Decides wether or not to purge (remove) from cobbler distro,
#     repo, profiles and systems which are not managed by puppet.
#     Default is true.
#
#   - default_kickstart [type: string]
#     Location of the default kickstart. Default depends on $::osfamily.
#
#   - webroot [type: string]
#     Location of Cobbler's web root. Default: '/var/www/cobbler'.
#
# Actions:
#   - Install Cobbler
#   - Manage Cobbler service
#
# Requires:
#   - puppetlabs/apache class
#     (http://forge.puppetlabs.com/puppetlabs/apache)
#
# Sample Usage:
#
class cobblerdata (
  $service_name       = $::cobblerdata::params::service_name,
  $package_name       = $::cobblerdata::params::package_name,
  $package_ensure     = $::cobblerdata::params::package_ensure,
  $distro_path        = $::cobblerdata::params::distro_path,
  $manage_dhcp        = $::cobblerdata::params::manage_dhcp,
  $dhcp_dynamic_range = $::cobblerdata::params::dhcp_dynamic_range,
  $manage_dns         = $::cobblerdata::params::manage_dns,
  $dns_option         = $::cobblerdata::params::dns_option,
  $dhcp_option        = $::cobblerdata::params::dhcp_option,
  $manage_tftpd       = $::cobblerdata::params::manage_tftpd,
  $tftpd_option       = $::cobblerdata::params::tftpd_option,
  $server_ip          = $::cobblerdata::params::server_ip,
  $next_server_ip     = $::cobblerdata::params::next_server_ip,
  $nameservers        = $::cobblerdata::params::nameservers,
  $dhcp_interfaces    = $::cobblerdata::params::dhcp_interfaces,
  $dhcp_subnets       = $::cobblerdata::params::dhcp_subnets,
  $defaultrootpw      = $::cobblerdata::params::defaultrootpw,
  $apache_service     = $::cobblerdata::params::apache_service,
  $allow_access       = $::cobblerdata::params::allow_access,
  $purge_distro       = $::cobblerdata::params::purge_distro,
  $purge_repo         = $::cobblerdata::params::purge_repo,
  $purge_profile      = $::cobblerdata::params::purge_profile,
  $purge_system       = $::cobblerdata::params::purge_system,
  $default_kickstart  = $::cobblerdata::params::default_kickstart,
  $webroot            = $::cobblerdata::params::webroot,
  $auth_module        = $::cobblerdata::params::auth_module
) inherits cobblerdata::params {

  #service { $service_name :
  #  ensure  => running,
  #  enable  => true,
  #  require => Package[$package_name],
  #}

  # file defaults
  File {
    ensure => file,
    owner  => root,
    group  => root,
    mode   => '0644',
  }

  file { $distro_path :
    ensure => directory,
    mode   => '0755',
  }
  file { "${distro_path}/kickstarts" :
    ensure => directory,
    mode   => '0755',
  }

  # cobbler sync command
  exec { 'cobblerdatasync':
    command     => '/usr/bin/cobbler sync',
    refreshonly => true,
  }

  # purge resources
  if $purge_distro == true {
    resources { 'cobblerdistro':  purge => true, }
  }
  if $purge_repo == true {
    resources { 'cobblerrepo':    purge => true, }
  }
  if $purge_profile == true {
    resources { 'cobblerprofile': purge => true, }
  }
  if $purge_system == true {
    resources { 'cobblersystem':  purge => true, }
  }

}
# vi:nowrap:
