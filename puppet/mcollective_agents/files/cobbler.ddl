metadata :name        => "cobbler",
     :description => "Handle specific cobbler commands",
     :author      => "Ericsson AB",
     :license     => "Ericsson",
     :version     => "1.0",
     :timeout     => 55, # this should exceed any xmlRPC timeout which may arise in a default apache/cobbler config
     :url         => "http://ericsson.com"


action "remove_system", :description => "removes given system" do
    display :always

    input :system,
          :prompt      => "System name",
          :description => "System name",
          :type        => :string,
          :optional    => false,
          :validation  => /^(\.[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])$/,
          :maxlength   => 62

    output :status,
           :description => "The status of the command",
           :display_as  => "remove system status",
           :default     => "unknown"
end

action "sync", :description => "sync cobbler" do
    display :always

    output :status,
           :description => "The status of the command",
           :display_as  => "sync cobbler status",
           :default     => "unknown"
end

action "add_system", :description => "add a cobbler system" do
    display :always

    input :system,
          :prompt      => "System name",
          :description => "System name",
          :type        => :string,
          :optional    => false,
          :validation  => /^(\.[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])$/,
          :maxlength   => 62

    input :profile,
          :prompt      => "Profile name",
          :description => "Profile name",
          :type        => :string,
          :optional    => false,
          :validation  => /^([a-zA-Z0-9._-]+)$/,
          :maxlength   => 62

    output :status,
           :description => "The status of the command",
           :display_as  => "add system status",
           :default     => "unknown"
end

action "edit_system", :description => "edit a cobbler system" do
    display :always

    input :system,
          :prompt      => "System name",
          :description => "System name",
          :type        => :string,
          :optional    => false,
          :validation  => /^(\.[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])$/,
          :maxlength   => 62

    input :profile,
          :prompt      => "Profile name",
          :description => "Profile name",
          :type        => :string,
          :optional    => true,
          :validation  => /^([a-zA-Z0-9._-]+)$/,
          :maxlength   => 62

    input :interface,
          :prompt      => "Interface",
          :description => "Interface name",
          :type        => :string,
          :optional    => true,
          :validation  => /^[a-z][a-z0-9]+$/,
          :maxlength   => 16 # see linux/if.h #define  IFNAMSIZ  16

    input :ip_address,
          :prompt      => "IP Address",
          :description => "IP Address",
          :type        => :string,
          :optional    => true,
          :validation  => /^[0-9.]+$/,
          :maxlength   => 253

    input :mac_address,
          :prompt      => "MAC Address",
          :description => "MAC Address",
          :type        => :string,
          :optional    => true,
          :validation  => /^([0-9A-Fa-f][0-9A-Fa-f]:){5}[0-9A-Fa-f][0-9A-Fa-f]$/,
          :maxlength   => 18

    input :hostname,
          :prompt      => "hostname",
          :description => "hostname",
          :type        => :string,
          :optional    => true,
          :validation  => /^.+$/,
          :maxlength   => 253

    input :dns_name,
          :prompt      => "dns_name",
          :description => "DNS name",
          :type        => :string,
          :optional    => true,
          :validation  => /^.+$/,
          :maxlength   => 253

    input :kickstart,
          :prompt      => "kickstart",
          :description => "Kickstart file name",
          :type        => :string,
          :optional    => true,
          :validation  => /^.+$/,
          :maxlength   => 255

    input :power_type,
          :prompt      => "power_type",
          :description => "Power Type",
          :type        => :string,
          :optional    => true,
          :validation  => /^[a-z]+$/,
          :maxlength   => 20

    input :virt_cpus,
          :prompt      => "virt_cpus",
          :description => "Number of virtual CPUs",
          :type        => :integer,
          :optional    => true

    input :virt_file_size,
          :prompt      => "virt_file_size",
          :description => "Size of disk images in GBs",
          :type        => :number,
          :optional    => true

    input :virt_path,
          :prompt      => "virt_path",
          :description => "Path of disk images",
          :type        => :string,
          :validation  => /^.+$/,
          :optional    => true,
          :maxlength   => 255

    input :virt_ram,
          :prompt      => "virt_ram",
          :description => "Ram of VMs in MBs",
          :type        => :integer,
          :optional    => true

    input :virt_type,
          :prompt      => "virt_type",
          :description => "Type of VMs",
          :type        => :string,
          :validation  => /^.+$/,
          :optional    => true,
          :maxlength   => 10

    output :status,
           :description => "The status of the command",
           :display_as  => "edit system status",
           :default     => "unknown"
end

action "create_directory", :description => "Create a backup directory" do
    display :always

    input :directory,
          :prompt      => "Name of directory to be created",
          :description => "Name of directory to be created",
          :type        => :string,
          :validation  => /^.+$/,
          :optional    => false,
          :maxlength   => 75

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
end

action "backup_anamon", :description => "backup anamon logs" do
    display :always

    input :system,
          :prompt      => "System name",
          :description => "System name",
          :type        => :string,
          :optional    => false,
          :validation  => /^(\.[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])$/,
          :maxlength   => 62

    output :status,
           :description => "The status of the command",
           :display_as  => "backup anamon status",
           :default     => "unknown"
end

action "remove_directory", :description => "Remove a backup directory" do
    display :always

    input :directory,
          :prompt      => "Name of directory to be removed",
          :description => "Name of directory to be removed",
          :type        => :string,
          :validation  => /^.+$/,
          :optional    => false,
          :maxlength   => 75

    output :status,
           :description => "The output of the command",
           :display_as  => "Command result",
           :default     => "no output"
end
