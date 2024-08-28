require 'xmlrpc/client'

Puppet::Type.type(:cobblerprofile).provide(:profile) do
  desc 'Support for managing the Cobbler profiles'

  commands :cobbler => '/usr/bin/cobbler'

  mk_resource_methods

  def self.instances
    keys = []
    # connect to cobbler server on localhost
    cobblerserver = XMLRPC::Client.new2('http://127.0.0.1/cobbler_api')
    # make the query (get all systems)
    xmlrpcresult = cobblerserver.call('get_profiles')

    # get properties of current system to @property_hash
    xmlrpcresult.each do |member|
      ks_opts_post_hash = {}
      member['kernel_options_post'].each do |key, val|
        ks_opts_post_hash["#{key}"] = val unless val == '' or val == []
      end
      kopts_hash = {}
      unless member['kernel_options'].nil?
          member['kernel_options'].each do |key, val|
            kopts_hash["#{key}"] = val unless val == '' or val == []
          end
      end
      keys << new(
        :name        => member['name'],
        :ensure      => :present,
        :distro      => member['distro'],
        :parent      => member['parent'],
        :nameservers => member['name_servers'],
        :repos       => member['repos'],
        :kickstart   => member['kickstart'],
        :kopts       => kopts_hash,
        :ks_opts_post  => ks_opts_post_hash
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

    # sets distribution (distro)
    def distro=(value)
      cobbler('profile', 'edit', '--name=' + @resource[:name], '--distro=' + value)
      @property_hash[:distro]=(value)
    end

    # sets parent profile
    def parent=(value)
      cobbler('profile', 'edit', '--name=' + @resource[:name], '--parent=' + value)
      @property_hash[:parent]=(value)
    end

    # sets kickstart
    def kickstart=(value)
      cobbler('profile', 'edit', '--name=' + @resource[:name], '--kickstart=' + value)
      @property_hash[:kickstart]=(value)
    end
    
    # sets kickstart options
    def ks_opts_post=(value)
      # set up kernel options
      ks_opt_post_value = []
      # if value is ~, that means key is standalone option
      value.each do |key,val|
        if val=="~"
          ks_opt_post_value << "#{key}"
        else
          ks_opt_post_value << "#{key}=#{val}" unless val=="~"
        end
      end

      cobbler('profile', 'edit', '--name=' + @resource[:name], '--kopts-post=' + ks_opt_post_value * ' ')
      @property_hash[:ks_opts_post]=(value)
    end

    # sets kernel options
    def kopts=(value)
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

      cobbler('profile', 'edit', '--name=' + @resource[:name], '--kopts=' + kopts_value * ' ')
      @property_hash[:kopts]=(value)
    end

    # sets nameservers
    def nameservers=(value)
      # create cobblerargs variable
      cobblerargs='profile edit --name=' + @resource[:name]
      # turn string into array
      cobblerargs = cobblerargs.split(' ')
      # set up nameserver argument 
      cobblerargs << ('--name-servers=' + value * ' ')
      # finally set value
      cobbler(cobblerargs)
      @property_hash[:nameservers]=(value)
    end

    # sets repos
    def repos=(value)
      # create cobblerargs variable
      cobblerargs='profile edit --name=' + @resource[:name]
      # turn string into array
      cobblerargs = cobblerargs.split(' ')
      # set up nameserver argument 
      cobblerargs << ('--repos=' + value * ' ')
      # finally set value
      cobbler(cobblerargs)
      @property_hash[:repos]=(value)
    end

    def create
      # check profile name
      raise ArgumentError, 'you must specify "distro" or "parent" for profile' if @resource[:distro].nil? and @resource[:parent].nil? 

      begin
        # remove previous if exists
        cobbler(['profile','remove','--name=' + @resource[:name]])
      rescue Puppet::ExecutionFailure => e
      end

      # create cobblerargs variable
      cobblerargs  = 'profile add --name=' + @resource[:name] 
      cobblerargs += ' --distro=' + @resource[:distro] unless @resource[:distro].nil?
      cobblerargs += ' --parent=' + @resource[:parent] unless @resource[:parent] != ''
      
      # turn string into array
      cobblerargs = cobblerargs.split(' ')

      # run cobbler commands
      cobbler(cobblerargs)

      # add kickstart, nameservers & repos (distro and/or parent are needed at creation time)
      # - check if property is defined, if not inheritance is probability (from parent)
      self.kickstart   = @resource.should(:kickstart)   unless @resource[:kickstart].nil?   or self.kickstart   == @resource.should(:kickstart)
      self.nameservers = @resource.should(:nameservers) unless @resource[:nameservers].nil? or self.nameservers == @resource.should(:nameservers)
      self.repos       = @resource.should(:repos)       unless @resource[:repos].nil?       or self.repos       == @resource.should(:repos)
      self.kopts   = @resource.should(:kopts)   unless @resource[:kopts].nil?   or self.kopts   == @resource.should(:kopts)
      self.ks_opts_post   = @resource.should(:ks_opts_post)   unless @resource[:ks_opts_post].nil?   or self.ks_opts_post   == @resource.should(:ks_opts_post)
      # final sync
      cobbler('sync')
      @property_hash[:ensure] = :present
    end

    def destroy
      # remove repository from cobbler
      cobbler('profile','remove','--name=' + @resource[:name])
      cobbler('sync')
      @property_hash[:ensure] = :absent
    end

    def exists?
      @property_hash[:ensure] == :present
    end
end
