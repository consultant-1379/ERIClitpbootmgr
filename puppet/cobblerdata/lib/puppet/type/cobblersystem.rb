Puppet::Type.newtype(:cobblersystem) do
@doc = "Manages the Cobbler system

A typical rule will look like this:

cobblersystem { 'test.domain.com':
  ensure         => present,
  profile        => 'CentOS-6.3-x86_64',
  interfaces     => { 
    'eth0' => {
      mac_address => '90:B1:1C:06:BF:56',
      static      => true,
      management  => true,
      ip_address  => '10.8.16.53',
      netmask     => '255.255.255.0',
      dns_name    => 'test.domain.com',
    },
  },
  kernel_options => {
    kssendmac => '~',
    noacpi    => '~',
    selinux   => 'permissive',
  },
  gateway        => '10.8.16.51',
  hostname       => 'test.domain.com',
  netboot        => false,
  kickstart      => 'file/path'
  comment        => 'my system description',
}

"
  desc 'The cobbler system type'

  ensurable

  newparam(:name) do
    isnamevar
    desc 'The name of the system'
  end

  newproperty(:profile) do
    desc 'Profile that is linked with system'
  end

  autorequire(:cobblerprofile) do
    self[:profile]
  end

  newproperty(:interfaces) do
    desc 'The list of interfaces in system.'

    def insync?(is)
      # @should is an Array. see lib/puppet/type.rb insync?
      should = @should.first

      # if members of hashes are not the same, something
      # was added or removed from manifest, so return false
      return false unless is.class == Hash and should.class == Hash and is.keys.sort == should.keys.sort
      # check if something was added or removed on second level
      is.each do |is_key,is_value|
        if is_value.is_a?(Hash)
          # hack for 'management' setting (which is being read all the time)
          #should[is_key].del('management') unless should[is_key].has_key?('management')
          if should[is_key].has_key?('management')
            should[is_key].delete('management')
          end
          # check every key in puppet manifest, leave the rest
          should[is_key].keys.uniq.each do |key|
            return false unless should[key] != is_value[key]
          end
        end
      end
      # if some setting changed in manifest, return false
      should.each do |k, v|
        if v.is_a?(Hash)
          v.each do |l, w|
            unless is[k][l].nil? 
               return false unless is[k][l].to_s == w.to_s
            end
          end 
        end 
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

  newproperty(:kernel_options) do
    desc "Kernel options for installation boot."
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

  newproperty(:gateway) do
    desc 'IP address of gateway.'
    defaultto ''
    validate do |value|
      unless value.chomp.empty?
        raise ArgumentError, "%s is not a valid IP address." % value unless value =~ /\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}/
      end
    end
  end

  newproperty(:kickstart) do
    desc 'Kickstart file used by profile'
  end
  autorequire(:file) do
    self[:kickstart]
  end

  newproperty(:hostname) do
    desc 'The hostname of the system, can be equal to name'
    defaultto ''
    validate do |value|
      unless value.chomp.empty?
        raise ArgumentError, "%s is not a valid hostname." % value unless value =~ /^(\.[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])$/
      end
    end
  end

  newproperty(:netboot) do
    desc 'Enable reinstallation of system.'
    newvalues(:true, :false)
  end

  newproperty(:comment) do
    defaultto ''
  end

  newproperty(:power_type) do
    defaultto 'ipmitool'
  end

  newproperty(:virt_cpus) do
    desc 'virtual cpus assigned by koan'
  end

  newproperty(:virt_file_size) do
    desc 'how large the disk image should be'
  end

  newproperty(:virt_path) do
    defaultto '<<inherit>>'
  end

  newproperty(:virt_ram) do
    defaultto '<<inherit>>'
  end

  newproperty(:virt_type) do
    defaultto 'qemu'
  end

end
