#!/usr/bin/python

import signal
import struct
import os
import socket
import sys
import time
from subprocess import Popen, PIPE



event_id_list = {
    "TOUCH":0x8001,
    "KEY":0x8002
}

# probe : (addr, arg_num, arg_fmt)
# probes : array [(addr1, arg_num1, arg_fmt1),
#                 (addr2, arg_num2, arg_fmt2)...]
# us_inst : (name, probes)
# libs_inst : array of lib_inst = (name, probes)
# app_inst : (us_inst, lib_inst)
# app_inst_list: [app_inst1, app_inst2, ...]
# features : array of features -> mask of used items from feature_list
# conf : (features, system_trace_period, data_message_period)
# replay : (state(1/0), start_time, events_list),
# if state=0, no more info
# event : (time, ID, ev_type, code, value)
# app_info : (app_type, app_id, exe_path)
#      app_type, app_id
# 01: tizen native application, the standard tizen native application ID
# 02: already launched process, PID
# 03: common executables, nothing

import string
import logging

def toprintable(s):
    if s in string.printable:
        if ord(s) == 0x0C: return '.'
        if ord(s) == 0x0A: return '.'
        if ord(s) == 0x0B: return '.'
        if ord(s) == 0x0D: return '.'
        if ord(s) == 0x08: return '.'
        if ord(s) == 0x09: return '.'
        return s
    else:
        return '.'

def print_buf(buf):
    count=0
    line=0
    str = ''
    for b in buf:
        sys.stderr.write( '%02X ' % ord(b) )
        str = str + toprintable(b) + ' '
        count = count + 1
        if count == 16:
            sys.stderr.write( '  %s | 0x%x\n' % (str, line * 16) )
            str = ''
            sys.stderr.flush
            count = 0
            line = line + 1
    for j in range(count,16):
        sys.stderr.write( '   ')
    sys.stderr.write( '  %s' % (str))
    for j in range(count,16):
        sys.stderr.write( '  ')

    sys.stderr.write( ' | 0x%x\n' % (line * 16))
    sys.stderr.flush

def alarm_handler(signum, frame):
    raise Exception

def exec_cmd(cmd, timeout=0):
    logging.debug(">>>> CMD <%s>" % cmd)
    if not signal.getsignal(signal.SIGALRM):
        signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(timeout)
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    out = out.decode()
    err = err.decode()
    signal.alarm(0)
    if p.returncode != 0:
        logging.debug(os.strerror(p.returncode))
        logging.debug("Error is %d: %s" % (p.returncode, os.strerror(p.returncode)))
        logging.debug("Stderr is %s" % (err))
        logging.debug("Stdout is %s" % (out))
    return p.returncode, out, err

class DeviceIntr(object):
    def __init__(self, exec_cmd_func=exec_cmd):
        self.exec_cmd = exec_cmd_func

    def push(src, dst, timeout=60):
        pass

    def shell(cmd, timeout=60):
        pass

    def root(st, timeout=60):
        pass

class DeviceIntrSDB(DeviceIntr):
    def __init__(self, is_emulator, exec_cmd_func=exec_cmd):
        self.target_type = "-e" if is_emulator else "-d"
        super(self.__class__, self).__init__(exec_cmd_func)

    def push(self, src, dst, timeout=60):
        res = self.exec_cmd("sdb %s push %s %s" % (self.target_type, src, dst), timeout)
        if res[0] != 0:
            return -1, None, None
        return res

    def shell(self, cmd, timeout=60):
        res = self.exec_cmd("sdb %s shell '%s'" % (self.target_type, cmd), timeout)
        if res[0] != 0:
            return -1, None, None
        return res

    def pull(self, src, dst, timeout=60):
		res = exec_cmd("sdb %s pull %s %s" % (self.target_type, src, dst), timeout)
		if res[0] != 0:
		    return -1, None, None
		return res

    def root(self, st, timeout=60):
		res = exec_cmd("sdb %s root %s" % (self.target_type, st), timeout)
		if res[0] != 0:
		    return -1, None, None
		return res

class DeviceIntrSSH(DeviceIntr):
    def __init__(self, username, host, ssh_params, exec_cmd_func=exec_cmd):
        self.ssh_params = ssh_params
        self.ssh_username = username
        self.ssh_host = host
        super(self.__class__, self).__init__(exec_cmd_func)

    def _get_scp_cmd(self, src, dst, is_push=True):
        params = ""
        if '-p' in self.ssh_params:
            params += "-P %s" % self.ssh_params['-p']
        if '-i' in self.ssh_params:
            params += ' ' + "-i '%s'" % self.ssh_params['-i']

        if is_push:
            cmd = "scp %s %s %s@%s:%s" % (params, src, self.ssh_username, self.ssh_host, dst)
        else:
            "scp %s %s@%s:%s %s" % (params, self.ssh_username, self.ssh_host, src, dst)
        return cmd

    def push(self, src, dst, timeout=60):
        res = exec_cmd(self._get_scp_cmd(src, dst), timeout)
        if res[0] != 0:
            return -1, None, None
        return res

    def shell(self, cmd, timeout=60):
        pList = ["%s@%s" % (self.ssh_username, self.ssh_host)] + \
            reduce(lambda res, x: res + x, [[p, str(self.ssh_params[p])] for p in self.ssh_params], [])
        params = ' '.join(map(lambda x: "'%s'" % x if ' ' in x.strip() else x, pList))
        res = self.exec_cmd("ssh %s '%s'" % (params, cmd), timeout)
        if res[0] != 0:
            return -1, None, None
        return res

    def pull(self, src, dst, timeout=60):
        res = self.exec_cmd(self._get_scp_cmd(src, dst, False), timeout)
        if res[0] != 0:
            return -1, None, None
        return res

class MsgHeader:
    def __init__(self, buf):
        resp = struct.unpack('IIi', buf[0:12])
        self.msg_id = resp[0]
        self.payload_len = resp[1]
        self.errcode = resp[2]
        self.data = buf[12: 12 + (self.payload_len - 4)]

class Connection:
    sock = None
    buf = []
    def __init__(self,ip,port):
        #self.server_address = ('localhost', 8001)
        self.server_address = (ip,port) #'192.168.129.3', 8001)
        logging.critical('connecting to %s port %s' % self.server_address)
        self.sock.connect(self.server_address)
        logging.debug("Connected" + str(self.sock))

    @classmethod
    def create_new_socket(class_obj):
        class_obj.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def __del__(self):
        logging.critical('closing socket' + str(self.sock))
        self.sock.close()

