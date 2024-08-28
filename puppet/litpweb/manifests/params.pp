class litpweb::params {

  File { require => Package['httpd'] }

  file {'/var/www/html/index.html':
    ensure  => file,
    content => template('litpweb/index.erb')
  }

}
