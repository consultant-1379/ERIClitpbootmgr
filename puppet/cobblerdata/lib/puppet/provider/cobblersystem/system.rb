require 'xmlrpc/client'

Puppet::Type.type(:cobblersystem).provide(:system) do
  desc 'Support for managing the Cobbler systems'

  commands :cobbler => '/usr/bin/cobbler'

  mk_resource_methods

  def self.instances
    keys = []
    # connect to cobbler server on localhost
    cobblerserver = XMLRPC::Client.new2('http://127.0.0.1/cobbler_api')
    # make the query (get all systems)
    xmlrpcresult = cobblerserver.call('get_systems')

    # get properties of current system to @property_hash
    xmlrpcresult.each do |member|
      # put only keys with values in interfaces hash
      inet_hash = {}
      member['interfaces'].each do |iface_name,iface_settings|
        inet_hash["#{iface_name}"] = {}
        iface_settings.each do |key,val|
          inet_hash["#{iface_name}"]["#{key}"] = val unless val == '' or val == []
        end
      end

      keys << new(
        :name           => member['name'],
        :ensure         => :present,
        :profile        => member['profile'],
        :interfaces     => inet_hash,
        :kernel_options => member['kernel_options'],
        :hostname       => member['hostname'],
        :gateway        => member['gateway'],
        :comment        => member['comment'],
        :kickstart      => member['kickstart'],
	
        :power_type     => member['power_type'],
	    :virt_cpus      => member['virt_cpus'].to_s,
        :virt_file_size => member['virt_file_size'].to_s,
	    :virt_path      => member['virt_path'],
	    :virt_ram	=> member['virt_ram'].to_s,
	    :virt_type	=> member['virt_type']
      )
    end
    keys
  end

  def self.prefetch(resources)
    instances.each do |prov|
      if resource = resources[prov.name]
        resource.provider = prov
      end
    end
  end

  # sets profile
  def profile=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--profile=' + value)
    cobbler('sync')
    @property_hash[:profile]=(value)
  end

  # sets hostname
  def hostname=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--hostname=' + value)
    cobbler('sync')
    @property_hash[:hostname]=(value)
  end

  # sets gateway
  def gateway=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--gateway=' + value)
    cobbler('sync')
    @property_hash[:gateway]=(value)
  end

  # sets kickstart
  def kickstart=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--kickstart=' + value)
    cobbler('sync')
    @property_hash[:kickstart]=(value)
  end

  # sets power_type
  def power_type=(value)
    if value.empty? == true
       value = "ipmitool"
    end
    cobbler('system', 'edit', '--name=' + @resource[:name], '--power-type=' + value)
    cobbler('sync')
    @property_hash[:power_type]=(value)
  end

  # sets virt_cpus
  def virt_cpus=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--virt-cpus=' + value)
    cobbler('sync')
    @property_hash[:virt_cpus]=(value)
  end

    # sets virt_file_size
  def virt_file_size=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--virt-file-size=' + value)
    cobbler('sync')
    @property_hash[:virt_file_size]=(value)
  end

  # sets power_type
  def virt_path=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--virt-path=' + value)
    cobbler('sync')
    @property_hash[:virt_path]=(value)
  end

  # sets virt_ram
  def virt_ram=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--virt-ram=' + value)
    cobbler('sync')
    @property_hash[:virt_ram]=(value)
  end

    # sets virt_type
  def virt_type=(value)
    if value.empty? == true
       value = "qemu"
    end
    cobbler('system', 'edit', '--name=' + @resource[:name], '--virt-type=' + value)
    cobbler('sync')
    @property_hash[:virt_type]=(value)
  end

  # sets interfaces
  def interfaces=(value)
    # name argument for cobbler
    namearg='--name=' + @resource[:name]

    # cobbler limitation: cannot delete all interfaces from system :(
    # so we must complicate interface sync by first adding temp
    # interface, then deleting/recreating all other interfaces
    # and finally deleting temp

    # connect to cobbler server on localhost
    cobblerserver = XMLRPC::Client.new2('http://127.0.0.1/cobbler_api')
    # make the query (get all systems)
    xmlrpcresult = cobblerserver.call('get_systems')
    # get properties of current system to variable
    currentsystem = {}
    xmlrpcresult.each do |member|
      currentsystem = member if member['name'] == @resource[:name]
    end
    # generate tmp string for interface name
    o =  [('a'..'z'),('A'..'Z')].map{|i| i.to_a}.flatten
    puppet_iface =  'tmp_' + (0...15).map{ o[rand(o.length)] }.join
    # add temp interface
    cobbler('system', 'edit', namearg, "--interface=#{puppet_iface}", '--static=true')
    # delete all other intefraces
    currentsystem['interfaces'].each do |iface_name,iface_settings|
      cobbler('system', 'edit', namearg, '--interface=' + iface_name, '--delete-interface')
    cobbler('sync')
    end

    # recreate interfaces according to resource in puppet
    value.each do |iface, settings|
      ifacearg = '--interface=' + iface

      settings.each do |key,val|
        # substitute _ for -
        setting = key.gsub(/_/,'-')
        # finally construct command and edit system properties
        unless val.nil?
          val = val.join(' ') if val.is_a?(Array)
          valuearg = "--#{setting}=" + val.to_s
          cobbler('system', 'edit', namearg, ifacearg, valuearg)
        else
          cobbler('system', 'edit', namearg, ifacearg, "--#{setting}=''")
        end
      end
    end

    # remove temp interface
    cobbler('system', 'edit', namearg, "--interface=#{puppet_iface}", '--delete-interface')
    cobbler('sync')

    @property_hash[:interfaces]=(value)
  end

  # sets kernel_options
  def kernel_options=(value)
    # name argument for cobbler
    namearg='--name=' + @resource[:name]

    # construct commandline from value hash
    cobblerargs='system edit --name=' + @resource[:name]
    cobblerargs=cobblerargs.split(' ')
    # set up kernel options
    kopts_value = []
    # if value is ~, that means key is standalone option
    value.each do |key,val|
      if val=="~"
        kopts_value << "#{key}"
      else
        kopts_value << "#{key}=#{val}" unless val=="~"
      end
    end
    cobblerargs << ('--kopts=' + kopts_value * ' ')
    # finally run command to set value
    cobbler(cobblerargs)
    # update property_hash
    @property_hash[:kernel_options]=(value)
  end

  # sets comment
  def comment=(value)
    cobbler('system', 'edit', '--name=' + @resource[:name], '--comment=' + value)
    @property_hash[:comment]=(value)
  end

  def create
    # add system
    cobbler('system', 'add', '--name=' + @resource[:name], '--profile=' + @resource[:profile], "--netboot-enabled=1")

    # add hostname, gateway, interfaces, netboot
    self.hostname       = @resource.should(:hostname)       unless @resource[:hostname].nil?    or self.hostname	== @resource.should(:hostname)
    self.gateway        = @resource.should(:gateway)        unless @resource[:gateway].nil?     or self.gateway		== @resource.should(:gateway)
    self.interfaces     = @resource.should(:interfaces)     unless self.interfaces     == @resource.should(:interfaces)
    self.comment        = @resource.should(:comment)        unless @resource[:comment].nil?        or self.comment	== @resource.should(:comment)
    self.kernel_options = @resource.should(:kernel_options) unless @resource[:kernel_options].nil? or self.kernel_options	== @resource.should(:kernel_options)
    self.kickstart      = @resource.should(:kickstart)      unless @resource[:kickstart].nil?      or self.kickstart	== @resource.should(:kickstart)
    self.power_type     = @resource.should(:power_type)     unless @resource[:power_type].nil?     or self.power_type
    self.virt_cpus      = @resource.should(:virt_cpus)      unless @resource[:virt_cpus].nil?      or self.virt_cpus	== @resource.should(:virt_cpus)
    self.virt_file_size = @resource.should(:virt_file_size) unless @resource[:virt_file_size].nil? or self.virt_file_size	== @resource.should(:virt_file_size)
    self.virt_path      = @resource.should(:virt_path)      unless @resource[:virt_path].nil?      or self.virt_path	== @resource.should(:virt_path)
    self.virt_ram       = @resource.should(:virt_ram)       unless @resource[:virt_ram].nil?       or self.virt_ram		== @resource.should(:virt_ram)
    self.virt_type      = @resource.should(:virt_type)      unless @resource[:virt_type].nil?      or self.virt_type	== @resource.should(:virt_type)

    # sync state
    cobbler('sync')

    # update @property_hash
    @property_hash[:ensure] = :absent
  end

  def destroy
    # remove system from cobbler
    cobbler('system', 'remove', '--name=' + @resource[:name])
    cobbler('sync')
    # update @property_hash
    @property_hash[:ensure] = :absent
  end

  def exists?
    @property_hash[:ensure] == :present
  end
end
