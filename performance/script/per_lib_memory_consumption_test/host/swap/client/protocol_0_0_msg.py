from client_lib import *
import signal
import struct
import os
import socket
import sys
import time
import tempfile
import logging

class Msg_v0_0(object):
    conf = {}
    def __init__(self, conf):
        self.msg_file = tempfile.mkstemp()[1]
        self.replay_file = tempfile.mkstemp()[1]
        self.conf = conf
        if not conf is None:
            self.proto_data = conf['proto_data']
        else:
            self.proto_data = None
        #logging.critical('MSG init conf = ' + str(conf))
        #logging.critical('MSG init proto_data = ' + str(self.proto_data))

        self.name = self.__class__.__name__
    def __del__(self):
        os.remove(self.msg_file)
        os.remove(self.replay_file)
        pass

    def send(self, filename=None, print_flag = 0):
        logging.critical("================ <%s> ================" % self.name)
        self.infile = open(self.msg_file, 'rb')
        self.message = self.infile.read()
        self.infile.close()
        if filename is None:
            logging.critical('sending message')
            if print_flag:
                print_buf(self.message)
            Connection.sock.sendall(self.message)
        else:
            logging.critical('save to file <%s>' % (filename))
            with open(filename,'w') as f:
                f.write(self.message)

    def recv(self, print_flag = 0):
        wait_s = 30.0
        self.msg_recv = None
        logging.critical('waiting for response... %ds' % wait_s)
        try:
            Connection.sock.settimeout(wait_s)
            resp_bin = Connection.sock.recv(12)
        except Exception as e:
            logging.critical('[ERROR] %s' % str(e))
            return None

        if len(resp_bin) <= 0:
            logging.critical('message len is 0')
            return self.msg_recv

        resp = struct.unpack('IIi', resp_bin[0:12])


        tail = resp[1] - 4 #4 byte it is error code
        resp_bin_add= ""

        #logging.critical("wait for data[%d]" % resp[1])

        while tail != 0:
            resp_bin_add = Connection.sock.recv(tail)
            tail = tail - len(resp_bin_add)
            resp_bin = resp_bin + resp_bin_add
            #logging.critical("%d %d; %d" % (len(resp_bin) ,len(resp_bin_add), tail))

        #logging.critical("%d %d; %d" % (len(resp_bin) ,len(resp_bin_add), tail))
        #logging.critical("total len = %d" % len(resp_bin))
        self.msg_recv = MsgHeader(resp_bin)
        return self.msg_recv

    def save(self,filename):
        self.send(filename)

    def parse(self, print_flag = 1):
        errcode = -1
        rcv_msg = self.msg_recv

        if print_flag != 0:
            msg_id = rcv_msg.msg_id
            msg_id_value = self.proto_data.msg_id_to_name(msg_id)
            payload_len = rcv_msg.payload_len
            errcode = rcv_msg.errcode

            logging.critical('msg_id : %04X = %s' % (msg_id, msg_id_value))
            logging.critical('payload len : %i' % (payload_len))
            logging.critical('errcode : %i (%s)' % (errcode, self.proto_data.return_id_list[errcode]))

#        logging.critical('[Err] class<%s> parser not implemented' % self.__class__.__name__)
        return None

    def parse_str(self, pos):
        str = ""
        payload = self.msg_recv.data

        while payload[pos] != '\0':
            str = str + payload[pos]
            pos = pos + 1
        pos = pos + 1
        return str

    def parse_uint32(self, pos):
        res = 0
        res = struct.unpack('i', self.msg_recv.data[pos:pos + 4])[0]
        return res

    def parse_uint64(self, pos):
        res = 0
        res = struct.unpack('Q', self.msg_recv.data[pos:pos + 8])[0]
        return res

    def open_msg_file_to_write(self):
        self.infile = open(self.msg_file, 'wb')

    def close_msg_file(self):
        self.infile.close()

    def open_replay_file_to_write(self):
        self.infile = open(self.replay_file, 'wb')

    def close_replay_file(self):
        self.infile.close()

    def write_int8(self, n):
        self.infile.write(struct.pack('B', n))

    def write_int32(self, n):
        self.infile.write(struct.pack('I', n))

    def write_int64(self, n):
        self.infile.write(struct.pack('q', n))

    def write_int128(self, n):
        n1 = n >> 64
        self.write_int64(n)
        self.write_int64(n1)

    def write_string(self, s):
        self.infile.write(s)
        self.infile.write(struct.pack('B', 0))

    def write_char(self, c):
        self.infile.write(c)

    def write_retprobe(self, args):
        self.write_string(args[0])
        self.write_char(args[1])

    def write_fbi_probe(self, args):
        self.write_int64(args[0])   # variable id
        self.write_int64(args[1])   # register offset
        self.write_int8 (args[2])   # register number
        self.write_int32(args[3])   # data size
        steps = args[4]
        steps_count = len(steps)/2
        self.write_int8(steps_count) # steps count
        for i in range(0, steps_count):
            self.write_int8(steps[i * 2 + 0])      # pointer order
            self.write_int64(steps[i * 2 + 1])     # data offset

    def write_ldprobe(self, args):
        #self.write_int64(args[0])
        self.write_string(args[1])
        self.write_char(args[2])

    def write_webprobe(self, args):
        pass

    def write_probe(self, addr, type, args):
        self.write_int64(addr)
        if self.conf["enable_probe_type_support"] == 1:
            self.write_int8(type)
        else:
            logging.debug("[WARNING] probe type DISABLED!!! use enable_probe_type_support=1 in conf")
            if type != 0:
                exit(1)

        if type == 0:
            self.write_retprobe(args)
        elif type == 1:
            self.write_int8(len(args))
            for probe in args:
                self.write_fbi_probe(probe)
        elif type == 2:
            self.write_ldprobe(args)
        elif type == 3:
            self.write_webprobe(args)
        else:
            logging.debug('write probe error. wrong probe type %s' % str(type))
            return 1
        return 0

    def write_us_inst(self, name, probes):
        self.write_string(name)
        self.write_int32(len(probes))
        #logging.critical( "name = %s" % (name))
        #logging.critical( "probes num = %d" % (len(probes)))
        for p in probes:
           # logging.critical( "> %s" % (str(p)))
            if self.write_probe(p[0], p[1], p[2]) != 0:
                return 1
        return 0

    def write_libs_inst(self, libs_inst):
        self.write_int32(len(libs_inst))
        for lib_inst in libs_inst:
            if self.write_us_inst(lib_inst, libs_inst[lib_inst]) != 0:
                return 1
        return 0

    def write_one_lib_inst(self, lib_name, lib_probes, first_probe = 0, last_probe = -1):
        self.write_int32(1)
        if self.write_us_inst(lib_name, lib_probes) != 0:
            return 1
        return 0

    def write_app_lcp(self, lcp):
        logging.debug("write_app_lcp")
        self.write_int64(lcp[0])
        #self.write_int8(0)

    def write_app_inst(self, app):
        #logging.critical('app_type %s, app_id %s, us_inst %s'  %(app_type, app_id, us_inst))
        self.write_int32(app['app_type'])
        self.write_string(app['app_id'])
        if self.write_us_inst(app['app_path'], app['app_probes']) != 0:
            return 1
        self.write_app_lcp(app['life_cycle_probes'])
        return 0

    def write_apps_inst(self, app_inst_list):
        #logging.critical('write app inst => ' + str(app_inst_list))
        for app in app_inst_list:
            logging.critical('write app inst app => ' + str(app))
            if self.write_app_inst(app) != 0:
                return 1
        return 0

    def write_us_app_inst(self, app_inst_list):
        logging.critical( "app num = %d" % (len(app_inst_list)))
        self.write_int32(len(app_inst_list))
        self.write_apps_inst(app_inst_list)

    def write_app_info(self, app_type, app_id, exe_path):
        self.write_int32(app_type)
        self.write_string(app_id)
        self.write_string(exe_path)

    def write_conf(self, conf):
        self.write_int128(conf['features'])
        self.write_int32(conf['system_trace_period'])
        self.write_int32(conf['data_message_period'])

    def write_size(self):
        self.size = self.infile.tell() - 8
        self.infile.seek(4, 0)
        self.write_int32(self.size)

    def write_time(self, time_sec, time_usec):
        self.write_int32(time_sec)
        self.write_int32(time_usec)

    def write_event(self, time_sec, time_usec, ID, ev_type, code, value):
        self.write_time(time_sec, time_usec)
        self.write_int32(ID)
        self.write_int32(ev_type)
        self.write_int32(code)
        self.write_int32(value)

    def write_replay(self, replay):
        if not replay is None:
            #self.write_int32(replay['type'])
            if replay['type'] == 1:
                self.write_time(replay['start_sec'], replay['start_usec'])
                self.write_int32(len(replay['events']))
                for ev in replay['events']:
                    self.write_event(ev[0], ev[1], ev[2], ev[3], ev[4], ev[5])
        else:
            logging.critical('no replays availible => ')
            #self.write_int32(0) #disabled
    def _default_prepare(self, msg_id):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        if isinstance(msg_id, basestring):
            self.write_int32(self.proto_data.msg_id_list[msg_id])
        else:
            self.write_int32(msg_id)
        # empty size
        self.write_int32(0)
        # close file
        self.close_msg_file()


