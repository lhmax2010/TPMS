#!/usr/bin/python
import os
import time
import shutil
import re
import socket
import threading
import logging

from client.client_lib import exec_cmd
from client.client import *

from library.status import *

class Environment():
    def __init__(self, cl, target_name, version = ""):
        # Check "trace_parser" utility
        if exec_cmd("trace_parser | grep Usage:")[0] != 0:
            exit_env("can not find \"trace_parser\" utility on your host")

#        if exec_cmd("tizen | grep Usage:")[0] != 0:
#            exit_env("can not find \"tizen\" utility on your host")

        self.cl = cl
        self.target_name = target_name
        self.version = version
        self.cpu_count = None
        cl.SetAPIMapPath(target_name + "/api_map_list")
        return

    def clean_artifacts(self):
        if os.path.exists(self.target_name):
            shutil.rmtree(self.target_name + "/screenshots", True)
            shutil.rmtree(self.target_name + "/tmp", True)
            shutil.rmtree(self.target_name)

    def prepare_host(self):
        # Remove testing artifacts
        self.clean_artifacts()

        # Create directory for output files
        os.mkdir(self.target_name)

        # Create temporary folder
        os.mkdir(self.target_name + "/tmp")
        os.close(os.open(self.target_name + "/tmp/__init__.py", os.O_CREAT|os.O_RDWR, 0666))

    def send_virt_event(self, event_file):
        logging.debug("Try to send event " + os.path.basename(event_file))
        return
        virttouch_dir = os.path.abspath(os.path.dirname(__file__) + "/../virttouch")
        exec_cmd(virttouch_dir + "/send_event.sh " + virttouch_dir + "/" + event_file + " " + self.cl.deviceIntr.target_type)

    def unblock_device(self):
        logging.debug("Try to unblock")

        self.send_virt_event("btn_power")
        self.send_virt_event("btn_power")
        self.send_virt_event("btn_home")
        self.send_virt_event("tch_drag2right")

    def push_binaries(self):
        res_path = os.path.abspath(os.path.dirname(__file__) + "/../resources")
        host_bin_path = os.path.abspath(res_path + "/" + self.target_name)
        ui_tpk_path = res_path + "/UI_apps/" + self.target_name

        if self.cl.deviceIntr.shell("mkdir -p /home/abuild")[0] != 0:
            exit_env("can not prepare target dirs")
        for app_inst in self.cl.conf['app_inst_list']:

            target_bin_full_name = app_inst['app_path']
            bin_name = re.sub(r'^.*/', '', target_bin_full_name)
            host_bin_full_name = host_bin_path + "/" + bin_name

            if app_inst['app_type'] == 2:
                return
            if app_inst['app_type'] == 1:
                logging.debug("### APP type native ###")
                ui_app_name = ""
                if app_inst['app_id'] == "":
                    logging.debug("Wrong app_id")
                    exit(1)
                for f in os.listdir(ui_tpk_path):
                    if re.search(app_inst['app_id'], f):
                        ui_app_name = f
                        exec_cmd(ui_tpk_path + "/../uninstall_package.sh " +
                                 app_inst['app_id'] + " " +
                                 self.cl.deviceIntr.target_type)
                        exec_cmd(ui_tpk_path + "/../install_package.sh " +
                                 ui_tpk_path + "/" + ui_app_name + " " +
                                 self.cl.deviceIntr.target_type)
                if ui_app_name == "":
                    logging.debug("tpk not found")
                return
            if app_inst['app_type'] == 4:
                logging.debug("### APP type Web ###")
                ui_app_name = ""
                if app_inst['app_id'] == "":
                    logging.debug("Wrong app_id")
                    exit(1)

                for filename in os.listdir(ui_tpk_path):
                    if re.search(app_inst['app_id'].split(".")[1], filename):
                        ui_app_name = filename
                        exec_cmd(ui_tpk_path + "/../uninstall_package.sh " +
                                 app_inst['app_id'].split(".")[0] + " " +
                                 self.cl.deviceIntr.target_type)
                        exec_cmd(ui_tpk_path + "/../install_package.sh " +
                                 ui_tpk_path + "/" + ui_app_name + " " +
                                 self.cl.deviceIntr.target_type)
                if ui_app_name == "":
                    logging.debug("tpk not found")
                return
            if not re.search(r'.shared$', bin_name) is None:
                # This is shared testcase
                lib_name = "lib" + re.sub(r'.shared$', '.so', bin_name)
                target_bin_path = os.path.dirname(target_bin_full_name)
                target_lib_full_name = target_bin_path + "/" + lib_name
                host_lib_full_name = host_bin_path + "/" + lib_name
                # Copy shared library to target
                if self.cl.deviceIntr.shell("rm -f " + target_lib_full_name)[0] != 0:
                    exit_env("can not remove previous testing library from target")
                if self.cl.deviceIntr.push(host_lib_full_name, target_lib_full_name)[0] != 0:
                    exit_env("can not push testing library to target")

            # Copy testcase to target
            if self.cl.deviceIntr.shell("rm -f " + target_bin_full_name)[0] != 0:
                exit_env("can not remove previous testing binary from target")
            if self.cl.deviceIntr.push(host_bin_full_name, target_bin_full_name)[0] != 0:
                exit_env("can not push testing binary to target")
            if self.cl.deviceIntr.shell("echo \"swap sdbd x\" | smackload")[0] != 0:
                exit_env("cannot set smack \"swap sdbd x\"")

    def prepare_target(self):
        # Load basic config
        if self.cl.LoadConfig("target." + self.target_name, "conf" + self.version) == 0:
            exit_env("can not load config for testcase")

        # Switch SDB in root mode
        if self.cl.deviceIntr.root("on")[0] != 0:
            exit_env("can not switch sdb into root mode")

        # Copy built binaries to target
        self.push_binaries()

        # Fix library and function names after test has been pushed to target
        if self.cl.ResolveConfig() == 0:
            exit_env("can not resolve config for testcase")

        # Clean dmesg log
        if self.cl.deviceIntr.shell("dmesg -c > /dev/null")[0] != 0:
            exit_env("can not clean dmesg on target")

        # Clean /tmp/da on target
        if self.cl.deviceIntr.shell("rm -rf /tmp/da/*")[0] != 0:
            exit_env("can not clean /tmp/da on target")

        # Run da_manager on target
        if self.cl.LaunchManager() != 0:
            exit_env("can not run da_manager on target")

        # unblock device
        self.unblock_device()

    def prepare_testing(self):
        self.prepare_host()
        self.prepare_target()
        self.get_core_num()

    def nc_thread(self, hostname, port, out_file):
        logging.debug("nc thread started")
        f = open(out_file, 'w')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((hostname, port))
        except:
            logging.debug("nc Unable to connect to " + str(hostname) + ":" + str(port))
            logging.debug(sys.exc_info()[0])
            return

        while True:
            data = s.recv(1024)
            if data == "":
                break
            f.write(data)
        logging.debug("nc Closed connection")
        s.close()
        f.close()
        logging.debug("nc thread finished")

    def start_nc(self, port):
        self.nc_t = threading.Thread(target=self.nc_thread,
                                     args=("127.0.0.1", int(port),
                                           self.target_name + "/trace.bin"))
        self.nc_t.setDaemon(True)
        self.nc_t.start()

    def stop_nc(self):
        self.nc_t.join(1)
        for i in range(30):
            if self.nc_t.isAlive():
                warn("nc is still running #" + str(i))
                time.sleep(1)
            else:
                logging.debug("netcat closed")
                break

    def get_core_num(self):
        if self.cpu_count == None:
            cmd = "getconf _NPROCESSORS_CONF"
            out = self.cl.deviceIntr.shell(cmd)
            if out[0] == -1:
                exit_env("cmd on target failed <%s>" % cmd)
            res = out[1].strip()
            if not res:
               exit_env("can not get CPU information from /proc/cpuinfo on target")
            self.cpu_count = res

        return int(self.cpu_count)

    def save_logs(self):
        cores = self.get_core_num()
        protocol_ver = self.cl.send.protocol_ver
        protocol_num = protocol_ver.replace(".", "")

        logging.debug("Converting SWAP trace into text format. cores = %d. protocol = %s" % (cores, protocol_ver))
        if exec_cmd("trace_parser -c%i -v%s -tp -f %s %s/trace.bin > %s/swap_trace.py" %\
                    (cores, protocol_num, self.cl.api_map_path, self.target_name, self.target_name))[0] != 0:

            exit_env("can not run trace_parser utility")

        return

        logging.debug("Saving daemon log")
        if self.cl.deviceIntr.pull("/tmp/daemonlog.da", self.target_name + "/daemonlog.da")[0] != 0:
            exit_env("can not get /tmp/daemonlog.da from target")

        logging.debug("Saving dmesg")
        if self.cl.deviceIntr.shell("dmesg > /tmp/dmesg")[0] != 0:
            exit_env("can not get dmesg on target")
        if self.cl.deviceIntr.pull("/tmp/dmesg", self.target_name + "/dmesg")[0] != 0:
            exit_env("can not get /tmp/dmesg from target")

        logging.debug("Saving uihv log")
        if self.cl.deviceIntr.pull("/tmp/uilib.log", self.target_name + "/uilib.log")[0] != 0:
            warn("can not get uilib.log on target")

        logging.debug("Saving screenshots")
        # curdir = os.getcwd()
        os.mkdir(self.target_name + "/screenshots")
        # os.chdir("screenshots")
        if self.cl.deviceIntr.pull("/tmp/da/", self.target_name + "/screenshots")[0] != 0:
            exit_env("can not get /tmp/da from target")

        # TODO screenshots getting. make it better.
        cmd = "ls /tmp/*.png; echo $?"
        out = self.cl.deviceIntr.shell(cmd)
        if out[0] == -1:
            exit_env("cmd on target failed <%s>" % cmd)
        else:
            res = out[1].replace("\n", " ").replace("\r", " ").strip().split()
            logging.debug(">>><%s>" % str(res))

            if res[-1] == '0':
                for f in res[:-1]:
                    logging.debug("<%s>" % f)
                    if f == "":
                        continue
                    if self.cl.deviceIntr.pull(f, self.target_name + "/screenshots")[0] != 0:
                        exit_env("can not get /tmp/*.png from target")

        logging.debug("Saving kallsyms")
        if self.cl.deviceIntr.shell("cat /proc/kallsyms > /tmp/kallsyms")[0] != 0:
            exit_env("can not get kallsyms on target")
        if self.cl.deviceIntr.pull("/tmp/kallsyms", self.target_name + "/kallsyms")[0] != 0:
            exit_env("can not get /tmp/kallsyms from target")

    def compare_results(self):
        # ToDo - implement results comparison routine
        return

    def finish_testing(self):
        # Save all logs coming from target
        self.save_logs()

        # Compare results of testing
        #self.compare_results()
