
class ssh::rootuser {

define sshuser {
  @user { $title: }

  @file { "/${title}":
    ensure => 'directory',
    mode   => '0700',
    owner  => $title,
    group  => $title,
  }

  @file { "/${title}/.ssh":
    ensure => 'directory',
    mode   => '0600',
    owner  => $title,
    group  => $title,
  }
  ssh::auth::key { $title: }
}

define sshclientuser {
  realize File["/${title}"]
  realize User[$title]
  realize File["/${title}/.ssh"]
  ssh::auth::client { $title: home => "/${title}", }
}

define sshserveruser ($ensure = 'present') {
  realize File["/${title}/.ssh"]
  User <| title == $title |> { ensure => $ensure }
  ssh::auth::server { $title: ensure  => $ensure, home => "/${title}", }
}

}
