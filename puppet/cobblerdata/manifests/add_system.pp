# Define: cobblerdata::add_system
define cobblerdata::add_system ($interfaces, $profile, $virt_data) {
  include cobblerdata
  
  if empty($virt_data) == false {
    $power_type     = $virt_data['power_type']
	$virt_cpus      = $virt_data['virt_cpus']
    $virt_file_size = $virt_data['virt_file_size']
	$virt_path      = $virt_data['virt_path']
	$virt_ram	    = $virt_data['virt_ram']
	$virt_type	    = $virt_data['virt_type']
	}
  else {
    $power_type     = undef
	$virt_cpus      = undef
    $virt_file_size = undef
	$virt_path      = undef
	$virt_ram	    = undef
	$virt_type	    = undef
  	}
   $ks_file = "/var/lib/cobbler/kickstarts/${title}.ks"
  cobblersystem { $title:
    ensure     => present,
    profile    => $profile,
    interfaces => $interfaces,
    hostname   => $title,
    require    => Cobblerprofile["${profile}"],
    kickstart  => $ks_file,
    power_type => $power_type,
	virt_cpus => $virt_cpus,
    virt_file_size => $virt_file_size,
	virt_path => $virt_path,
	virt_ram => $virt_ram,
	virt_type => $virt_type,
   }

}


