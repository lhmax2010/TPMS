#!/usr/bin/python

import logging
import client_lib
import gen_bin

import os
import time
import config
import fcntl
import re
from subprocess import *
from client_lib import *
from denote import *

from protocol_0_0 import Send_v0_0
from protocol_3_0 import Send_v3_0
from protocol_4_0 import Send_v4_0
from protocol_4_1 import Send_v4_1
from protocol_4_2 import Send_v4_2

#cfg = Config('base_tests')
#cfg = Config()
#cfg = Config('./test_gen/conf/test.conf')
#generated_conf = cfg.GetConfig(1) #replays on
#generated_conf = cfg.GetConfig(0) # replays off
REPLAY_ENABLE = 1
REPLAY_DISABLE = 0

class Client(object):
    def __init__(self):
        self.conf = None
        self.connection = None
        self.gen = gen_bin.Generator()
        self.send = Send_v0_0()
        self.deviceIntr = DeviceIntr()
        self.local_port = 8001
        self.SetAPIMapPath('api_map_list')
        self.denote = None
        return

    def __del__(self):
        sdb_add = '-d' if not self.conf['target_is_virtual'] else '-e'

        logging.debug("sdb " + sdb_add + " forward --remove tcp:" + str(self.local_port))
        p = Popen(["sdb", sdb_add, "forward", "--remove", "tcp:" + str(self.local_port)],
                  stdout=PIPE, stderr=PIPE)
        out, err = p.communicate()
        out = out.decode()
        err = err.docode()
        if p.returncode != 0:
            print("[WARNING] " + str(err))

    def get_port(self):
        for i in range(1,10):
            if self.deviceIntr.pull("/tmp/port.da", "/tmp/port.da")[0] == -1:
                logging.debug("can not get /tmp/port.da from target")
                return None
            port_file = open("/tmp/port.da", "r")
            port = port_file.read()
            port = int(port.split('\n')[-1])
            port_file.close()
            os.remove("/tmp/port.da")
            return port

    def forward_port(self, rport, lport):
        target_is_virtual = self.conf['target_is_virtual']
        if target_is_virtual == 0:
            sdb_add = '-d'
        else:
            sdb_add = '-e'
        logging.debug("sdb " + sdb_add + " forward tcp:" + str(lport) + " tcp:" + str(rport) + " ")
        p = Popen(["sdb", sdb_add, "forward","tcp:" + str(lport) , "tcp:" + str(rport)], stdout=PIPE, stderr=PIPE)
        out, err = p.communicate()
        out = out.decode()
        err = err.decode()
        if p.returncode != 0:
            logging.debug("[WARNING] %s" % str(err))
        return

    def get_free_local_port_and_forward(self, rport):
        # lock file /tmp/swap_test.lock
        print("Try to lock /tmp/swap_test.lock")
        with open("/tmp/swap_test.lock", "w+") as f:
            fcntl.lockf(f, fcntl.LOCK_EX)
            port_candidate = 8001
            sdb_add = '-d' if self.conf['target_is_virtual'] else '-e'

            p = Popen(["sdb", sdb_add, "forward", "--list"],
                      stdout=PIPE, stderr=PIPE)
            out, err = p.communicate()
            out = out.decode()
            err = err.decode()
            if p.returncode != 0:
                print("[WARNING] " + str(err))

            used_ports = re.findall("tcp:(\d*)\s*tcp:\d*", out)
            while str(port_candidate) in used_ports:
                port_candidate += 1

            self.local_port = port_candidate
            self.forward_port(rport, self.local_port)

            fcntl.lockf(f, fcntl.LOCK_UN)

    def SetTargetType(self, target_type = ""):
        if target_type == "-d" or target_type == 0:
            self.conf['target_is_virtual'] = 0
        elif target_type == "-e" or target_type == 1:
            self.conf['target_is_virtual'] = 1
        else:
            logging.debug("[ERROR] wrong target type <%s>" % str(target_type))
            return 0
        return 1

    def SetAPIMapPath(self, path):
        self.api_map_path = path

    def Connect(self):
        target_is_virtual = self.conf['target_is_virtual']

        if self.conf['target_port'] is None:
            self.conf['target_port'] = self.get_port()
        if self.conf['target_port'] is None:
            logging.debug("can not get port from device")
            return None
        elif target_is_virtual == 1 or self.conf['connection_type'] == "sdb":
            self.get_free_local_port_and_forward(self.conf['target_port'])

        target_ip = self.conf['target_ip']
        target_port = self.conf['target_port']

        rebooted = 0
        retryCount = 0
        while True:
            client_lib.Connection.create_new_socket()
            if self.conf['connection_type'] == 'sdb':
                target_port = self.local_port
                logging.debug('trying to connect "%s:%d"' % (target_ip, self.local_port))
                self.connection = client_lib.Connection(target_ip, self.local_port)
            else:
                logging.debug('trying to connect "%s:%d"' % (target_ip, target_port))
                self.connection = client_lib.Connection(target_ip, target_port)

            if retryCount == 10 and not rebooted:
                logging.debug('[ERROR] get protocol version 10 times failed')
                os.system("sdb shell reboot")
                time.sleep(30)
                retryCount = -1
            if retryCount == 10 and not rebooted:
                logging.debug('[ERROR] We are totally screwed')
                return None
            if self.send.GetProtoVersion() is None:
                logging.debug('[ERROR] get protocol version failed')
                del self.connection
                time.sleep(1)
                retryCount += 1
                if retryCount >= 3:
                    raise Exception("Failed to get SWAP protocol version")
            else:
                break

        protocol_ver = self.send.protocol_ver
        logging.debug("Protocol version = <%s>" % protocol_ver)
        if protocol_ver == '3.0':
            self.send = Send_v3_0(self.deviceIntr)
        elif protocol_ver == '4.0':
            self.send = Send_v4_0(self.deviceIntr)
        elif protocol_ver == '4.1':
            self.send = Send_v4_1(self.deviceIntr)
        elif protocol_ver == '4.2':
            self.send = Send_v4_2(self.deviceIntr)
        elif protocol_ver == '':
            logging.debug("[WARNING] protocol is not seted. Use default v4.2")
            self.send = Send_v4_2(self.deviceIntr)
        else:
            logging.debug("Protocol version unsuported")

        # Get API map list
        if protocol_ver == '3.0':
            #
            if self.deviceIntr.pull("/usr/lib/da_api_map", self.api_map_path)[0] == -1:
                logging.debug('[ERR] cannot get API map list')
        else:
            # protocol_ver >= 4.0
            msg = self.send.GetAPIMap(0)
            if msg is None:
                logging.debug('msg GetAPIMap failed')
            else:
                f = open(self.api_map_path, 'w')
                if not f is None:
                    for n in msg.parsed:
                        f.write('%s %s\n' % (n - 1, msg.parsed[n]))
                    f.close()
                else:
                    logging.debug("[ERR] cannot create API map list file")

        self.send.SetConf(self.conf)

        return target_port

    def Disconnect(self):
        if not self.connection is None:
            del self.connection
        return

    def LoadConfig(self, target_conf_name, test_conf_path):
        self.configurator = config.Config()
        if self.configurator is None:
            return 0
        if self.configurator.LoadConfig(target_conf_name, test_conf_path) == 0:
            return 0

        return self.SetConf(self.configurator.GetConfig(1))

    def SetConf(self, conf):
        self.conf = conf
        if self.conf is None:
            return 0
        self.send.SetConf(self.conf)
        if self.send.conf is None:
            return 0
        self.gen.conf = self.conf
        if self.gen.conf is None:
            return 0

        if self.conf['connection_type'] == "ssh":
            self.deviceIntr = DeviceIntrSSH(self.conf['ssh_username'], self.conf['target_ip'], self.conf['ssh_params'])
            self.gen.deviceIntr = self.deviceIntr
        else:
            self.deviceIntr = DeviceIntrSDB(self.conf['target_is_virtual'])
            self.gen.deviceIntr = self.deviceIntr

        return 1

    def ResolveConfig(self):
        if self.denote == None:
            self.denote = Denote()

        if self.denote.resolve_config(self) is None:
            return 0
        return 1

    def SetFeatures(self, new_features):
        logging.debug(self.conf)
        logging.debug(self.send.conf['conf'])
        f, stp, dmp = self.send.conf['conf']
        self.send.conf['conf']["features"] = 0x0000000000000000 + new_features;

        return 1

    def LaunchManager(self):
        cmd = self.conf['da_manager_exec_cmd']

        change_buf_cmd = ""
        if 'subbuf_size' in self.conf and 'subbuf_count' in self.conf:
            subbuf_size = self.conf['subbuf_size']
            subbuf_count = self.conf['subbuf_count']

            change_buf_cmd += "echo 0 > /sys/kernel/debug/swap/driver/buffer_enabled;"
            change_buf_cmd += "echo %d > /sys/kernel/debug/swap/driver/subbuf_size;" % subbuf_size
            change_buf_cmd += "echo %d > /sys/kernel/debug/swap/driver/subbuf_conunt;" % subbuf_count
            change_buf_cmd += "echo 1 > /sys/kernel/debug/swap/driver/buffer_enabled;"

        logging.debug('launch da on target with <%s> cmd' % cmd)


        res = self.deviceIntr.shell("ps afx | grep -v grep | grep da_manager || %s; sleep 15; %s" % (cmd, change_buf_cmd))
        if res[0] != 0:
            logging.debug("run fail %s" % res)
            return 1
        logging.debug("run success")
        return 0
