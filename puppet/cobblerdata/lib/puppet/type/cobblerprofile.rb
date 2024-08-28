Puppet::Type.newtype(:cobblerprofile) do
@doc = "Manages the Cobbler profiles

A typical rule will look like this:

cobblerprofile {'CentOS-6.3-x86_64':
  ensure        => present,
  distro        => 'CentOS-6.3-x86_64',
}"
 
  desc 'The cobbler profile type'

  ensurable

  newparam(:name) do
    isnamevar
    desc 'The name of the profile'
  end

  newproperty(:distro) do
    desc 'Distribution this profile is based on'
  end
  autorequire(:cobblerdistro) do
    self[:distro]
  end

  newproperty(:parent) do
    defaultto ''
    desc 'Parent profile that this profile is based on'
  end
  autorequire(:cobblerprofile) do
    self[:parent]
  end

  newproperty(:kickstart) do
    desc 'Kickstart file used by profile'
  end
  autorequire(:file) do
    self[:kickstart]
  end

  newproperty(:kopts) do
    desc 'kopts used by profile'
    defaultto Hash.new

    def insync?(is)
      # @should is an Array. see lib/puppet/type.rb insync?
      should = @should.first

      # if members of hashes are not the same, something
      # was added or removed from manifest, so return false
      return false unless is.class == Hash and should.class == Hash and is.keys.sort == should.keys.sort
      # check if values of hash keys are equal
      is.each do |l,w|
        return false unless w == should[l]
      end
      true
    end

    def should_to_s(newvalue)
      newvalue.inspect
    end

    def is_to_s(currentvalue)
      currentvalue.inspect
    end
  end

  newproperty(:ks_opts_post) do
    desc 'kopts-post used by profile'
    defaultto Hash.new
    
    def insync?(is)
      # @should is an Array. see lib/puppet/type.rb insync?
      should = @should.first

      # if members of hashes are not the same, something
      # was added or removed from manifest, so return false
      return false unless is.class == Hash and should.class == Hash and is.keys.sort == should.keys.sort
      # check if values of hash keys are equal
      is.each do |l,w|
        return false unless w == should[l]
      end
      true
    end

    def should_to_s(newvalue)
      newvalue.inspect
    end

    def is_to_s(currentvalue)
      currentvalue.inspect
    end
  end

  newproperty(:nameservers, :array_matching => :all) do
    desc 'List of nameservers for this profile'
    # http://projects.puppetlabs.com/issues/10237
    def insync?(is)
      return false unless is == should
      true
    end
  end

  newproperty(:repos, :array_matching => :all) do
    desc "list of repositories added to profile"
    # http://projects.puppetlabs.com/issues/10237
    def insync?(is)
      return false unless is == should
      true
    end

  end
  autorequire(:cobblerrepo) do
    self[:repos]
  end

end
