#!/usr/bin/python

import logging

import client_lib
import protocol_3_0

from client_lib import *
from protocol_0_0 import Send_v0_0
from protocol_0_0 import _local_data_0_0
from protocol_3_0_msg import Msg_v3_0

_msg_id_list = {
    "MSG_KEEP_ALIVE":0x0001,
    "MSG_START":0x0002,
    "MSG_STOP":0x0003,
    "MSG_CONFIG":0x0004,
    "MSG_BINARY_INFO":0x0005,
    "MSG_GET_TARGET_INFO":0x0007,
    "MSG_SWAP_INST_ADD":0x0008,
    "MSG_SWAP_INST_REMOVE":0x0009,
    "MSG_LIFECYCLE_TIMING":0x000A,
    "MSG_GET_SCREENSHOT":0x0010,
    "MSG_GET_PROCESS_ADD_INFO":0x0011,
    "MSG_GET_UI_HIERARCHY":0x0012,
    "MSG_GET_UI_SCREENSHOT":0x0013,
    "MSG_GET_UI_HIERARCHY_CANCEL":0x0014,
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
    "MSG_KEEP_ALIVE_ACK":0x1001,
    "MSG_START_ACK":0x1002,
    "MSG_STOP_ACK":0x1003,
    "MSG_CONFIG_ACK":0x1004,
    "MSG_BINARY_INFO_ACK":0x1005,
    "MSG_GET_TARGET_INFO_ACK":0x1007,
    "MSG_SWAP_INST_ADD_ACK":0x1008,
    "MSG_SWAP_INST_REMOVE_ACK":0x1009,
    "MSG_LIFECYCLE_TIMING_ACK":0x000A,
    "MSG_GET_SCREENSHOT_ACK":0x1010,
    "MSG_GET_PROCESS_ADD_INFO_ACK":0x1011
}


class _local_data_3_0(_local_data_0_0):
    def __init__(self):
        super(_local_data_3_0, self).__init__()

        self.response_msg_id_list = _response_msg_id_list
        self.feature_list = _feature_list
        self.msg_id_list = _msg_id_list

class MsgKeepAlive(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        self._default_prepare("MSG_KEEP_ALIVE")

class MsgStart(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self, deviceIntr, replay_enable = 0, first_probe = 0, last_probe = None):
        conf = self.conf['conf']
        app_inst_list = self.conf['app_inst_list']
        if replay_enable == 1:
            replay = self.conf['replay']
        else:
            logging.debug("replays disabled")
            replay = None
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_START"])
        # empty size
        self.write_int32(0)
        # apps inst
        # TODO fix kostyl with [0]
        res = app_inst_list[0]['app_probes']
        if last_probe is None:
            res = res[first_probe:]
        else:
            res = res[first_probe:last_probe]

        if not res is None:
            app_inst_list[0]['app_probes'] = res
            self.write_us_app_inst(app_inst_list)
        else:
            logging.debug('[ERROR] start is none')
            return 1

        # apps inst
        #self.write_apps_inst(app_inst_list)
        # replay
        # size
        self.write_int32(replay_enable)
        self.write_replay(replay)

        self.write_size()
        # close file
        self.close_msg_file()

class MsgSwapInstAdd(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self, name, pr_num, first_probe = 0, last_probe = None):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_SWAP_INST_ADD"])
        # empty size
        self.write_int32(0)
        # apps inst
        #self.write_user_space_inst(self.conf['user_space_inst_list'])
        # libs inst
        if name == "":
            #print "!!! %s" % str(self.conf)
            if self.write_libs_inst(self.conf['lib_inst_list'][pr_num]) != 0:
                return 1
        else:
            pr_list = self.conf['lib_inst_list'][pr_num][name]

            if last_probe is None:
                res = pr_list[first_probe:]
            else:
                res = pr_list[first_probe:last_probe]

            if not res is None:
                self.write_one_lib_inst(name, res)
            else:
                logging.debug('[ERROR] lib <%s> not found' % name)
                return 1

        # size
        self.write_size()
        # close file
        self.close_msg_file()
        return 0

class MsgSwapKernelAdd(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self, deviceIntr):
        #print self.conf

        list = self.conf['app_inst_list'][0]['kernel_probes']

        deviceIntr.shell("echo \"0\" > /sys/kernel/debug/swap/ksm/enable")

        deviceIntr.shell("echo \"c\" > /sys/kernel/debug/swap/ksm/cmd")
        for probe in list:
            #print "echo \"a %s:%s >\" /sys/kernel/debug/swap/ksm/cmd" % (probe[0], probe[1])
            deviceIntr.shell("echo \"a %s:%s\" > /sys/kernel/debug/swap/ksm/cmd" % (probe[1], probe[0]))

        deviceIntr.shell("echo \"1\" > /sys/kernel/debug/swap/ksm/enable")
        return 0



class MsgSwapInstRemove(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self, pr_num):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_SWAP_INST_REMOVE"])
        # empty size
        self.write_int32(0)
        # apps inst
        if self.write_libs_inst(self.conf['lib_inst_list'][pr_num]) != 0:
            return 1
        # size
        self.write_size()
        # close file
        self.close_msg_file()
        return 0

class MsgStop(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_STOP"])
        # empty size
        self.write_int32(0)
        # close file
        self.close_msg_file()

class MsgScreenShot(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_GET_SCREENSHOT"])
        # empty size
        self.write_int32(0)
        # close file
        self.close_msg_file()
        return 0

class MsgGetProcessAddInfo(Msg_v3_0):
    def prepare(self, pidarr):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_GET_PROCESS_ADD_INFO"])
        # empty size
        self.write_int32(0)
        # pid count
        self.write_int32(len(pidarr))
        for i in pidarr:
            self.write_int32(i)
        # size
        self.write_size()
        # close file
        self.close_msg_file()
        return 0

    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)

        resp_bin = self.msg_recv.data
        print_buf(resp_bin)

        pos = 0
        pidcount = self.parse_uint32(pos)
        pos = pos + 4

        logging.critical('pid count : %i ' % (pidcount))

        for i in range(0, pidcount):
            cmd_line = ""
            pid = self.parse_uint32(pos)
            pos = pos + 4

            cmd_line = self.parse_str(pos)
            pos = pos + len(cmd_line) + 1

            logging.critical('#app_%i <%i> <%s>' % (i+1, pid, cmd_line))
        return self.msg_recv

class MsgLifecycleTimingConfig(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')

        app_inst_list = self.conf['app_inst_list']

        # type
        logging.debug(self.proto_data.msg_id_list)
        self.write_int32(self.proto_data.msg_id_list["MSG_LIFECYCLE_TIMING"])
        # empty size
        self.write_int32(0)
        # apps count
        self.write_int32(1)
        # app path
        self.write_string(app_inst_list[0]["app_path"])
        # configuration
        self.write_int64(app_inst_list[0]["life_cycle_probes"][0])
        self.write_int64(app_inst_list[0]["life_cycle_probes"][1])
        # size
        self.write_size()
        # close file
        self.close_msg_file()
        return 0


class MsgConfig(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_CONFIG"])
        # empty size
        self.write_int32(0)
        # configuration
        self.write_conf(self.conf['conf'])
        # function offsets (needs for web profiling)
        if None not in self.conf['addr']:
            for a in self.conf['addr']:
                self.write_int64(a)
        # size
        self.write_size()
        # close file
        self.close_msg_file()
        return 0


class MsgBinaryInfo(Msg_v3_0):
    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_BINARY_INFO"])
        # apps
        app_inst_list = self.conf['app_inst_list']
        # dummy size
        self.write_int32(0)
        # binary count
        self.write_int32(len(app_inst_list))
        for app in app_inst_list:
            self.write_string(app['app_path'])

        # size
        self.write_size()
        # close file
        self.close_msg_file()
        return 0

    def parse(self, print_flags = 0):
        super(Msg, self).parse(print_flags)

        rcv_msg = self.msg_recv
        payload = rcv_msg.data

        pos = 0
        app_count = self.parse_uint32(pos)
        pos = pos + 4

        logging.critical('application count : %i ' % (app_count))
        for i in range(0, app_count):
            logging.critical('#app_%i ' % (i+1))
            app_local_path = ""
            app_md5 = ""
            app_type = -1

            app_type = self.parse_uint32(pos)
            pos = pos + 4

            app_local_path = self.parse_str(pos)
            pos = pos + len(app_local_path) + 1

            app_md5 = self.parse_str(pos)
            pos = pos + len(app_md5) + 1

            logging.critical(' type       : %i ' % (app_type))
            logging.critical(' local path : %s ' % (app_local_path))
            logging.critical(' md5        : %s ' % (app_md5))


        return rcv_msg

class MsgSwapInst(Msg_v3_0):
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_SWAP_INST"])
        # empty size
        self.write_int32(0)
        # us_inst, libs_inst
        self.write_apps_inst(self.conf['app_inst_list'])
        # size
        self.write_size()
        # close file
        self.close_msg_file()
        return 0


class MsgGetTargetInfo(Msg_v3_0):
    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_GET_TARGET_INFO"])
        # empty size
        self.write_int32(0)
        # close file
        self.close_msg_file()
        return 0

    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)

        resp_bin = self.msg_recv.data

        print_buf(resp_bin)
        if print_flags != 0:
            pos = 0
            system_mem_size = self.parse_uint64(pos)
            storage_size    = self.parse_uint64(pos + 8)
            bluetooth_sup   = self.parse_uint32(pos + 16)
            gps_sup         = self.parse_uint32(pos + 20)
            wifi_sup        = self.parse_uint32(pos + 24)
            camera_count    = self.parse_uint32(pos + 28)
            pos = pos + 32
            network_type    = self.parse_str(pos)
            pos = pos + len(network_type) + 1
            max_brightnes   = self.parse_uint32(pos + 0)
            num_of_cpu      = self.parse_uint32(pos + 4)
            num_of_dev      = self.parse_uint32(pos + 8)
            pos = pos + 12


            logging.critical('system mem size : %i' % (system_mem_size))
            logging.critical('storage size    : %i' % (storage_size))
            logging.critical('bluetooth supp  : %i' % (bluetooth_sup))
            logging.critical('gps supp        : %i' % (gps_sup))
            logging.critical('wifi supp       : %i' % (wifi_sup))
            logging.critical('camera count    : %i' % (camera_count))

            logging.critical('network type    : <%s>' % (network_type))
        # pr = struct.unpack('II', resp_bin[-8:])

            logging.critical('max brightness  : 0x%08X' % (max_brightnes))
            logging.critical('CPU core count  : %i' % (num_of_cpu))
            logging.critical('Dev num         : %i' % (num_of_dev))
            for i in range(0, num_of_dev):
                str = self.parse_str(pos)
                pos = pos + len(str) + 1
                logging.critical(' #%d            :<%s>' % (i + 1, str))


        return self.msg_recv

class MsgGetUIhierarhy(Msg_v3_0):
    def prepare(self, rendering_time_option):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_GET_UI_HIERARCHY"])
        # size = 1
        self.write_int32(1)
        # write rendering option
        self.write_int8(rendering_time_option)
        # close file
        self.close_msg_file()
        return 0
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

class MsgGetUIscreenshot(Msg_v3_0):
    def prepare(self, ui_object_address):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_GET_UI_SCREENSHOT"])
        # size = 1
        self.write_int32(8)
        # write ui_object_address
        self.write_int64(ui_object_address)
        # close file
        self.close_msg_file()
        return 0
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

class MsgGetUIhierarhyCancel(Msg_v3_0):
    def prepare(self):
        # open file
        self.open_msg_file_to_write()
        logging.critical('writing message')
        # type
        self.write_int32(self.proto_data.msg_id_list["MSG_GET_UI_HIERARCHY_CANCEL"])
        # size = 1
        self.write_int32(0)
        # close file
        self.close_msg_file()
        return 0
    def parse(self, print_flags = 0):
        super(self.__class__, self).parse(print_flags)
        return self.msg_recv

class Send_v3_0(Send_v0_0):
#Send methods
    def __init__(self, deviceIntr):
        self.deviceIntr = deviceIntr
        self.protocol_ver = "3.0"
        self.proto_data = _local_data_3_0()
        self.SetConf(None)
        return

    def CheckConf(self, print_flags = 0):
        if self.conf is None:
            logging.debug('[Error(%s)] config not loaded' % self.__class__)
            return -1
        return 0

    def KeepAlive(self, print_flags = 0):
        msg = protocol_3_0.MsgKeepAlive(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)

    def LifecycleTimingConfig(self, print_flags = 0):
        msg = protocol_3_0.MsgLifecycleTimingConfig(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)


    def Config(self, print_flags = 0):
        if self.CheckConf() == -1:
            return
        msg = protocol_3_0.MsgConfig(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)

    def Bin(self, print_flags = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgBinaryInfo(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)

    def Start(self, enableval, first_probe = 0, last_probe = None, print_flags = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgStart(self.conf)
        msg.prepare(self.deviceIntr, enableval, first_probe, last_probe)
        return self.SendAndWait(msg, print_flags)

    def Add(self, pr_num = 0, print_flags = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgSwapInstAdd(self.conf)
        if msg.prepare("", pr_num) != 0:
            return None
        return self.SendAndWait(msg, print_flags)

    def AddKernel(self, print_flags = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgSwapKernelAdd(self.conf)
        if msg.prepare(self.deviceIntr) != 0:
            return None
        return self

    def AddByName(self, name = "", first_probe = 0, last_probe = None, pr_num = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgSwapInstAdd(self.conf)
        res = msg.prepare(name, pr_num, first_probe, last_probe)

        if res != 0:
            return None
        return self.SendAndWait(msg, print_flags)

    def Remove(self, pr_num, print_flags = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgSwapInstRemove(self.conf)
        msg.prepare(pr_num)
        return self.SendAndWait(msg, print_flags)

    def Stop(self, print_flags = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgStop(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)

    def GetTargetInfo(self, print_flags = 0):
        if self.CheckConf() == -1:
            return None
        msg = protocol_3_0.MsgGetTargetInfo(self.conf)
        msg.prepare()
        return self.SendAndWait(msg, print_flags)

    def ScreenShot(self, print_flags = 0):
        msg = protocol_3_0.MsgScreenShot(self.conf)
        msg.prepare()
        return msg.send()

    def GetProcessAddInfo(self, pidarr, print_flags = 0):
        msg = protocol_3_0.MsgGetProcessAddInfo(self.conf)
        msg.prepare(pidarr)
        return self.SendAndWait(msg, print_flags)
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
#
#
#    def Recv(self):
#        msg = protocol_3_0.MsgConfig(self.conf)
#        msg.prepare()
#        resv_res = msg.recv()
#        del msg
#        if resv_res != 0:
#            print "[Error(%s)] recv err %d" % (self.__class__, resv_res)
#            exit(resv_res)
#        return resv_res


