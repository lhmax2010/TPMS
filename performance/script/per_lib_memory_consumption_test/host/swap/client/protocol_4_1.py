#!/usr/bin/python

import client_lib
import protocol_4_0
import protocol_3_0

from client_lib import *
from protocol_4_0 import Send_v4_0
from protocol_4_0 import _local_data_4_0
from protocol_4_1_msg import Msg_v4_1


_msg_id_list = {
    "MSG_VERSION":0x0001,
    "MSG_START":0x0002,
    "MSG_STOP":0x0003,
    "MSG_CONFIG":0x0004,
    "MSG_BINARY_INFO":0x0005,
    "MSG_GET_TARGET_INFO":0x0007,
    "MSG_SWAP_INST_ADD":0x0008,
    "MSG_SWAP_INST_REMOVE":0x0009,
    "MSG_GET_PROBEMAP":0x000A,
    "MSG_KEEP_ALIVE":0x000F,
    "MSG_GET_SCREENSHOT":0x0010,
    "MSG_GET_PROCESS_ADD_INFO":0x0011,
    "MSG_GET_UI_HIERARCHY":0x0012,
    "MSG_GET_UI_SCREENSHOT":0x0013,
    "MSG_GET_UI_HIERARCHY_CANCEL":0x0014,
    "MSG_GET_REAL_PATH":0x0020,


    "MSG_HZ_HZ_HZ":0x0FFF
}

_feature_list = {
    "CPU":                                  2 ** 0,  #0x00000000000001,
    "memory":                               2 ** 1,  #0x00000000000002,
    "function profiling":                   2 ** 2,  #0x00000000000004,
    "memory allocation probing":            2 ** 3,  #0x00000000000008,
    "file API probing":                     2 ** 4,  #0x00000000000010,
    "thread API probing":                   2 ** 5,  #0x00000000000020,
    "OSP UI API probing":                   2 ** 6,  #0x00000000000040,
    "screenshot":                           2 ** 7,  #0x00000000000080,
    "user event":                           2 ** 8,  #0x00000000000100,
    "recording":                            2 ** 9,  #0x00000000000200,
    "syscall file":                         2 ** 10, #0x00000000000400,
    "syscall ipc":                          2 ** 11, #0x00000000000800,
    "syscall process":                      2 ** 12, #0x00000000001000,
    "syscall signal":                       2 ** 13, #0x00000000002000,
    "syscall network":                      2 ** 14, #0x00000000004000,
    "syscall desc":                         2 ** 15, #0x00000000008000,
    "context switch":                       2 ** 16, #0x00000000010000,
    "network API probing":                  2 ** 17, #0x00000000020000,
    "openGL API probing":                   2 ** 18, #0x00000000040000,
    "function sampling ":                   2 ** 19, #0x00000000080000
    "memory allcation probing nofilter ":   2 ** 28, #0x00000010000000,
    "file API probing nofilter":            2 ** 29, #0x00000020000000,
    "thread API probing nofilter":          2 ** 30, #0x00000040000000,
    "OSP UI API probing nofilter":          2 ** 31, #0x00000080000000,
    "network API probing nofilter":         2 ** 32, #0x00000100000000,
    "openGL API probing nofilter":          2 ** 33, #0x00000200000000,
    "SYSTEM_CPU":                           2 ** 36, #0x00001000000000,
    "SYSTEM_MEMORY ":                       2 ** 37, #0x00002000000000,
    "SYSTEM_PROCESS":                       2 ** 38, #0x00004000000000,
    "SYSTEM_THREAD_LOAD":                   2 ** 39, #0x00008000000000,
    "SYSTEM_PROCESSES_LOAD ":               2 ** 40, #0x00010000000000,
    "SYSTEM_DISK":                          2 ** 41, #0x00020000000000,
    "SYSTEM_NETWORK":                       2 ** 42, #0x00040000000000,
    "SYSTEM_DEVICE":                        2 ** 43, #0x00080000000000,
    "SYSTEM_ENERGY":                        2 ** 44, #0x00100000000000,
    "APP_STARTUP":                          2 ** 45, #0x00200000000000,
    "WEB_PROFILING":                        2 ** 46, #0x00400000000000,
    "WEB_STARTUP_PROFILING":                2 ** 47, #0x00800000000000,
    "system file activity":                 2 ** 48, #0x01000000000000,
    "FL_UI_VIEWER_PROFILING":               2 ** 49, #0x02000000000000, # New

}

_response_msg_id_list = {
    "MSG_VERSION_ACK":0x1001,
    "MSG_START_ACK":0x1002,
    "MSG_STOP_ACK":0x1003,
    "MSG_CONFIG_ACK":0x1004,
    "MSG_BINARY_INFO_ACK":0x1005,
    "MSG_GET_TARGET_INFO_ACK":0x1007,
    "MSG_SWAP_INST_ADD_ACK":0x1008,
    "MSG_SWAP_INST_REMOVE_ACK":0x1009,
    "MSG_GET_PROBEMAP_ACK":0x100A,
    "MSG_KEEP_ALIVE_ACK":0x100F,
    "MSG_GET_SCREENSHOT_ACK":0x1010,
    "MSG_GET_PROCESS_ADD_INFO_ACK":0x1011,
    "MSG_GET_UI_HIERARCHY_ACK":0x1012,
    "MSG_GET_UI_SCREENSHOT_ACK":0x1013,
    "MSG_GET_UI_HIERARCHY_CANCEL_ACK":0X1014

}

class _local_data_4_1(_local_data_4_0):
    def __init__(self):
        super(_local_data_4_1, self).__init__()

        self.msg_id_list = _msg_id_list;
        self.feature_list = _feature_list;
        self.response_msg_id_list = _response_msg_id_list;

class Send_v4_1(Send_v4_0):
#Send methods
    def __init__(self, deviceIntr):
        self.deviceIntr = deviceIntr
        self.conf = None
        self.protocol_ver = "4.1"
        self.proto_data = _local_data_4_1()
        self.SetConf(None)
        return
#New
    def GetUIhierarhy(self, rendering_time_option, print_flags = 0):
        msg = protocol_3_0.MsgGetUIhierarhy(self.conf)
        msg.prepare(rendering_time_option)
        return self.SendAndWait(msg, print_flags)

    def GetUIscreenshot(self, ui_object_address, print_flags = 0):
        msg = protocol_3_0.MsgGetUIscreenshot(self.conf)
        msg.prepare(ui_object_address)
        return self.SendAndWait(msg, print_flags)

    def GetUIhierarhyCancel(self, print_flags = 0):
        msg = protocol_3_0.MsgGetUIhierarhyCancel(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)
