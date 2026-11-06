#!/usr/bin/python

import logging
import client_lib
import protocol_4_0
import protocol_3_0

from client_lib import *
from protocol_3_0 import Send_v3_0
from protocol_3_0 import _local_data_3_0
from protocol_4_0_msg import Msg_v4_0

_msg_id_list = {
    "MSG_VERSION":0x0001,                   #MSG_KEEP_ALIVE -> MSG_VERSION
    "MSG_START":0x0002,
    "MSG_STOP":0x0003,
    "MSG_CONFIG":0x0004,
    "MSG_BINARY_INFO":0x0005,               #message format changed
    "MSG_GET_TARGET_INFO":0x0007,
    "MSG_SWAP_INST_ADD":0x0008,
    "MSG_SWAP_INST_REMOVE":0x0009,
    "MSG_GET_PROBEMAP":0x000A,              #NEW
    "MSG_KEEP_ALIVE":0x000F,                #move from 0x0001 -> 0x000F
    "MSG_GET_SCREENSHOT":0x0010,
    "MSG_GET_PROCESS_ADD_INFO":0x0011,
    "MSG_GET_REAL_PATH":0x0020,

    "MSG_HZ_HZ_HZ":0x0FFF
}

_feature_list = {
    "CPU":0x0001,
    "memory":0x0002,
    "function profiling":0x0004,
    "memory allocation probing":0x0008,
    "file API probing":0x0010,
    "thread API probing":0x0020,
    "OSP UI API probing":0x0040,
    "screenshot":0x0080,
    "user event":0x0100,
    "recording":0x0200,
    "syscall file":0x0400,
    "syscall ipc":0x0800,
    "syscall process":0x1000,
    "syscall signal":0x2000,
    "syscall network":0x4000,
    "syscall desc":0x8000,
    "context switch":0x10000,
    "network API probing":0x20000,
    "openGL API probing":0x40000
}

_response_msg_id_list = {
    "MSG_VERSION_ACK":0x1001,               #MSG_KEEP_ALIVE_ACK -> MSG_VERSION_ACK
    "MSG_START_ACK":0x1002,
    "MSG_STOP_ACK":0x1003,
    "MSG_CONFIG_ACK":0x1004,
    "MSG_BINARY_INFO_ACK":0x1005,
    "MSG_GET_TARGET_INFO_ACK":0x1007,
    "MSG_SWAP_INST_ADD_ACK":0x1008,
    "MSG_SWAP_INST_REMOVE_ACK":0x1009,
    "MSG_GET_PROBEMAP_ACK":0x100A,          #NEW
    "MSG_KEEP_ALIVE_ACK":0x100F,            #move from 0x1001 -> 0x100F
    "MSG_GET_SCREENSHOT_ACK":0x1010,
    "MSG_GET_PROCESS_ADD_INFO_ACK":0x1011,
    "MSG_GET_REAL_PATH_ACK":0x1020,
}

class _local_data_4_0(_local_data_3_0):
    def __init__(self):
        super(_local_data_4_0, self).__init__()

        self.msg_id_list = _msg_id_list;
        self.feature_list = _feature_list;
        self.response_msg_id_list = _response_msg_id_list;

class MsgGetAPImap(Msg_v4_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)

        recv_msg = self.msg_recv
        self.parsed = {};
        if (not recv_msg is None):
            if recv_msg.payload_len <= 4:
                logging.debug("msg payload length = %d" % recv_msg.payload_len)
                return recv_msg;
            data = recv_msg.data
            pos = 0
            count = self.parse_uint32(0)
            pos = pos + 4
            for i in range(0, count):
                id = self.parse_uint32(pos)
                pos = pos + 4

                name = self.parse_str(pos)
                pos = pos + len(name) + 1

                if print_flags != 0:
                    logging.debug("[%d] %s" % (id, name))
                self.parsed[id] = name;
        else:
            logging.debug(not recv_msg is None)
            logging.debug(print_flags)
        if recv_msg is None:
            return None
        else:
            return self

    def prepare(self):
        self._default_prepare("MSG_GET_PROBEMAP")

class MsgKeepAlive(Msg_v4_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        self._default_prepare("MSG_KEEP_ALIVE")

class MsgHz(Msg_v4_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        self._default_prepare("MSG_HZ_HZ_HZ")

class MsgGetRealPath(Msg_v4_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)

        rcv_msg = self.msg_recv
        payload = rcv_msg.data

        pos = 0
        resolved_path = self.parse_str(pos)
        logging.critical(' resolved path   : %s ' % (resolved_path))

        return self.msg_recv

    def prepare(self, path_to_resolve = ""):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_GET_REAL_PATH"])
        # empty size
        self.write_int32(0)
        # path to resolve
        self.write_string(path_to_resolve)

        self.write_size()
        # close file
        self.close_msg_file()

class MsgBinaryInfo(protocol_3_0.MsgBinaryInfo):
    def parse(self, print_flags = 0):
        #super(protocol_3_0.MsgBinaryInfo, self).parse(print_flags)
        super(Msg, self).parse(print_flags)

        rcv_msg = self.msg_recv
        payload = rcv_msg.data

        pos = 0
        app_count = self.parse_uint32(pos)
        pos = pos + 4

        logging.critical('application count : %i ' % (app_count))
        for i in range(0, app_count):
            logging.critical('#app_%i ' % (i+1))
            app_bin_path = ""
            app_local_path = ""
            app_md5 = ""
            app_type = -1

            app_path = self.parse_str(pos)
            pos = pos + len(app_path) + 1

            app_type = self.parse_uint32(pos)
            pos = pos + 4

            app_local_path = self.parse_str(pos)
            pos = pos + len(app_local_path) + 1

            app_md5 = self.parse_str(pos)
            pos = pos + len(app_md5) + 1

            logging.critical(' bin path   : %s ' % (app_bin_path))
            logging.critical(' type       : %i ' % (app_type))
            logging.critical(' local path : %s ' % (app_local_path))
            logging.critical(' md5        : %s ' % (app_md5))


        return rcv_msg

class Send_v4_0(Send_v3_0):
#Send methods
    def __init__(self, deviceIntr):
        self.deviceIntr = deviceIntr
        self.protocol_ver = "4.0"
        self.proto_data = _local_data_4_0()
        self.SetConf(None)
        return

    def Hz(self, id):
        msg = client_lib.MsgHz(self.conf)
        msg.prepare(id)
        return self.SendAndWait(msg)

    def Bin(self):
        if self.CheckConf() == -1:
            return None
        msg = protocol_4_0.MsgBinaryInfo(self.conf)
        msg.prepare()
        return self.SendAndWait(msg)

    def GetAPIMap(self, print_flags = 0):
        msg = protocol_4_0.MsgGetAPImap(self.conf)
        msg.prepare()
        if self.SendAndWait(msg, print_flags) is None:
            return None
        else:
            return msg

    def ScreenShot(self, print_flags = 0):
        msg = protocol_3_0.MsgScreenShot(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)

    def GetRealPath(self, file_path, print_flags = 0):
        msg = protocol_4_0.MsgGetRealPath(self.conf)
        msg.prepare(file_path)
        return self.SendAndWait(msg, print_flags)

#New
    def GetUIhierarhy(self, rendering_time_option, print_flags = 0):
        error = '[Error(%s)] MSG_GET_UI_HIERARCHY does not supported by <%s>' % (self.__class__, self.protocol_ver)
        raise NameError(error)
        return None

    def GetUIscreenshot(self, ui_object_address, print_flags = 0):
        error = ('[Error(%s)] MSG_GET_UI_SCREENSHOT does not supported by <%s>' % (self.__class__, self.protocol_ver))
        raise NameError(error)
        return None

    def GetUIhierarhyCancel(self, print_flags = 0):
        error = ('[Error(%s)] MSG_GET_UI_HIERARCHY_CANCEL does not supported by <%s>' % (self.__class__, self.protocol_ver))
        raise NameError(error)
        return None
