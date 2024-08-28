require 'syslog'

module MCollective
  module Agent
    class Cobbler<RPC::Agent
      begin
        PluginManager.loadclass("MCollective::Util::LogAction")
        log_action = Util::LogAction
      rescue LoadError => e
        raise "Cannot load logaction util: %s" % [e.to_s]
      end

      action "sync" do
        cmd = "cobbler sync"
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action "remove_system" do
        cmd = "cobbler system remove --name=#{request[:system]}"
        log_action.debug(cmd, request)
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        if reply[:out].include?("unknown system name") then
          # ignoring removal of non-existing node
          reply[:status] = 0
          reply[:out] = "system #{request[:system]} does not exist, no action taken"
        end
        # cobbler sends errors to stdout in this case
        if reply[:status] != 0 then
          reply[:err] = reply[:err] + reply[:out]
        end
      end

      action "add_system" do
        cmd = "cobbler system add " +
              "--name=#{request[:system]} " +
              "--profile=#{request[:profile]} "
        Log.debug(cmd)
        ss = []; request.data.each {|k, v| ss << "#{k} => #{v}"; };
        Log.debug('{' + ss * ',' + '}')
        reply[:status] = run("#{cmd}",
          :stdout => :out,
          :stderr => :err,
          :chomp => true)
        # cobbler sends errors to stdout in this case
        reply[:err] = reply[:err] + reply[:out]
      end

      action "edit_system" do
        cmd = "cobbler system edit " +
              "--name=#{request[:system]} "
        req_data = request.data.clone
        if req_data.has_key?(:mac_address)
            req_data[:mac] = req_data[:mac_address]
            req_data.delete(:mac_address)
        end
        req_data.delete(:system)
        req_data.delete(:process_results)
        req_data.each {|k, v|
                      kd = k.to_s.gsub('_', '-')
                      cmd += "--#{kd}=#{v} "
                      }
        Log.debug(cmd)
        ss = []; req_data.each {|k, v| ss << "#{k} => #{v}"; };
        Log.debug('{' + ss * ',' + '}')
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        # cobbler sends errors to stdout in this case
        reply[:err] = reply[:err] + reply[:out]
      end

      action "create_directory" do
         cmd = "mkdir -p #{request[:directory]}"
         reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
         log_action.debug("Outcome: #{reply[:status]}", request)
      end

      action "backup_anamon" do
        cmd = "rsync -a /var/log/cobbler/anamon/#{request[:system]} " +
              "/var/log/cobbler/anamon.backup/#{request[:system]}." +
              "$(date +'%Y.%m.%d-%H.%M.%S')/"
        reply[:status] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action "remove_directory" do
         cmd = "rm -rf #{request[:directory]}"
         reply[:status] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
         log_action.debug("Outcome: #{reply[:status]}", request)
      end
    end
  end
end

