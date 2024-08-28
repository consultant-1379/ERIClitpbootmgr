
define ssh::rootconfig ($master='false', $user='true', $client='true', $server='true') {

  include ssh::auth
  include ssh::rootuser

  if $master == 'true' {
    include ssh::auth::keymaster
  }

  if $user == 'true' {
    ssh::rootuser::sshuser {[ 'root' ]: }
  }

  if $client == 'true' {
    ssh::rootuser::sshclientuser {[ 'root' ]: }
  }

  if $server == 'true' {
    ssh::rootuser::sshserveruser {[ 'root' ]: }
  }

}
