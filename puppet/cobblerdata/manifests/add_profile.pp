# Define: cobblerdata::add_profile
define cobblerdata::add_profile ($distro,$kickstart,$ks_opts_post,$kopts=[],$repos=[]) {
  include cobblerdata
  
  cobblerprofile { $title :
    ensure       => present,
    distro       => $distro,
    kickstart    => $kickstart,
    ks_opts_post => $ks_opts_post,
    kopts        => $kopts,
    repos        => $repos,
    require    => Cobblerdistro["${distro}"],
  }

}

