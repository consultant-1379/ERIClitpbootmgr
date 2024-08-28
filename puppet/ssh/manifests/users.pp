
class ssh::users {

define sshuser {
  @user { $title: }

  @file { '/users':
    ensure => 'directory',
    mode   => '0755',
    owner  => 'root',
    group  => 'root',
  }

  @file { "/users/${title}":
    ensure => 'directory',
    mode   => '0700',
    owner  => $title,
    group  => $title,
  }

  @file { "/users/${title}/.ssh":
    ensure => 'directory',
    mode   => '0600',
    owner  => $title,
    group  => $title,
  }
  ssh::auth::key { $title: }
}

define sshclientuser {
  realize File['/users']
  realize File["/users/${title}"]
  realize User[$title]
  realize File["/users/${title}/.ssh"]
  ssh::auth::client { $title: home => "/users/${title}", }
}

define sshserveruser ($ensure = 'present') {
  realize File["/users/${title}/.ssh"]
  User <| title == $title |> { ensure => $ensure }
  ssh::auth::server { $title:
    ensure => $ensure,
    home   => "/users/${title}",
  }
}

}
