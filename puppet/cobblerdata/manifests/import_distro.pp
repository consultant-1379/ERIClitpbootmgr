# Define: cobbler::import_distro
define cobblerdata::import_distro ($arch,$path,$breed,$os_version,$url_path='') {
  include cobblerdata
  if $url_path == '' {
      $tree = { }
  }
  else {
      $tree_value = "http://@@http_server@@/${url_path}"
      $tree = { 'tree' =>$tree_value }
  }
  $initrd = "/var/www/cobbler/ks_mirror/${title}/images/pxeboot/initrd.img"
  $kernel = "/var/www/cobbler/ks_mirror/${title}/images/pxeboot/vmlinuz"
  cobblerdistro { $title :
    ensure     => present,
    arch       => $arch,
    path       => $path,
    ks_meta    => $tree,                         
    breed      => $breed,
    os_version => $os_version,
    comment    => $os_version,
    initrd     => $initrd,
    kernel     => $kernel,
    require    => [Service[$cobblerdata::service_name]],
  }

}



