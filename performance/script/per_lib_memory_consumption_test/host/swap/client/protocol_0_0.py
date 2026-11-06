#!/usr/bin/python

import logging

import client_lib
import protocol_0_0
from protocol_0_0_msg import Msg_v0_0

from client_lib import *

_msg_id_list = {
    "MSG_VERSION":0x0001,
}

_feature_list = {

}

_response_msg_id_list = {
    "MSG_KEEP_ALIVE_ACK":0x1001,
}

_return_id_list = {
    0:"success",
    -1:"internat error",
    -101:"lock file create failed",
    -102:"already running",
    -103:"initialize system info failed",
    -104:"host server socket create failed",
    -105:"target server socket create failed",
    -201:"wrong message format",
    -202:"wrong message type",
    -203:"wrong message data",
    -204:"cannot start profiling",
    -900:"server socket creation failed (written in /tmp/da.port file)",
    -901:"server socket bind failed (written in /tmp/da.port file)",
    -902:"server socket listen failed (written in /tmp/da.port file)",
    -999:"unknown error"
}


class _local_data_0_0(object):
    def __init__(self):
        self.msg_id_list = _msg_id_list;
        self.feature_list = _feature_list;
        self.response_msg_id_list = _response_msg_id_list;
        self.return_id_list = _return_id_list;

    def msg_id_to_name(self, msg_id):
        # TODO refactor it
        for msg_id_key in self.response_msg_id_list:
            if self.response_msg_id_list[msg_id_key] == msg_id:
                return msg_id_key
        return "no value in dict"


class MsgGetProtoVersion(Msg_v0_0):
    def prepare(self):
        self._default_prepare("MSG_VERSION")

    def parse(self, print_flag = 0):
        return self

class MsgRecved:
    def __init__(self, buffer):
        self.id = buffer[0];
        self.payload_len = buffer[1];
        self.return_id = buffer[2];
        self.payload = buffer;

        return

class Send_v0_0:
    def __init__(self):
        self.protocol_ver = "0.0"
        self.proto_data = _local_data_0_0()
        self.SetConf(None)
        return

    def SetConf(self, conf):
        self.conf = conf
        if self.conf is None:
            self.conf = {}
        self.conf['proto_data'] = self.proto_data
        #print "Send_v0_0 CONFIG SET!!! %s" % str(self.conf)
        return

    def _GetKeyByID(self, msg_id):
        for msg_id_key in self.proto_data.response_msg_id_list:
            if self.proto_data.response_msg_id_list[msg_id_key] == msg_id:
                return msg_id_key
        return 'no value in dict'



    def SendAndWait(self, msg, print_flags = 0):
        msg.send()
        msg_recv = msg.recv()
        if msg_recv is None:
            logging.debug("[Error(%s)] recv err %s" % (self.__class__, str(msg_recv)))
            return msg_recv

        if msg.parse(print_flags) is None:
            logging.debug("[Error(%s)] cannot parse" % (self.__class__))
            return None
        return msg_recv

    def GetProtoVersion(self):
        msg = protocol_0_0.MsgGetProtoVersion(self.conf)
        msg.prepare()
        res = self.SendAndWait(msg)

        if not res is None:
            #print_buf(res.data)
            logging.debug("version = %s" % res.data)
            self.protocol_ver = "%s" % res.data[0:-1]
            logging.debug("<%s>" % self.protocol_ver)
        else:
            self.protocol_ver = "3.0"
        return res



