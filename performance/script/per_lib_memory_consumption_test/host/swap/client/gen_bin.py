#!/usr/bin/python

import logging

from client_lib import *
import time

class Generator():
    def __init__(self):
        self.deviceIntr = None
        self.conf = None
        return

    def check(self, dir):
        d = os.path.dirname(dir)
        if not os.path.exists(d):
            logging.debug('[Error(%s)] cannot save bins to "%s" directory' % (self.__class__, dir))
            return -1
        if self.conf is None:
            logging.debug('[Error(%s)] config not loaded' % (self.__class__))
            return -1
        return 1

    def GenKeepAlive(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgKeepAlive(self.conf)
        test_msg.prepare()
        test_msg.save(path_to_save + '/keep_alive.bin')
        del test_msg

    def GenConfig(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgConfig(self.conf)
        test_msg.prepare()
        test_msg.save(path_to_save + '/config.bin')
        del test_msg

    def GenBin(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgBinaryInfo(self.conf)
        test_msg.prepare(app_info)
        test_msg.save(path_to_save + '/bin.bin')
        del test_msg

    def GenStart(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgStart(self.conf)
        test_msg.prepare(self.deviceIntr, 1)
        test_msg.save(path_to_save + '/start.bin')
        del test_msg

    def GenAdd(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgSwapInstAdd(self.conf)
        test_msg.prepare()
        test_msg.save(path_to_save + '/add.bin')
        del test_msg

    def GenRemove(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgSwapInstRemove(self.conf)
        test_msg.prepare()
        test_msg.save(path_to_save + '/remove.bin')
        del test_msg

    def GenStop(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgStop(self.conf)
        test_msg.prepare()
        test_msg.save(path_to_save + '/stop.bin')
        del test_msg

    def GenGetTargetInfo(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        test_msg = MsgGetTargetInfo(self.conf)
        test_msg.prepare()
        test_msg.save(path_to_save + '/get_target_info.bin')
        del test_msg

    def GenAllBins(self, path_to_save):
        if self.check(path_to_save) == -1:
            return -1
        self.GenStart(path_to_save)
        self.GenAdd(path_to_save)
        self.GenRemove(path_to_save)
        self.GenConfig(path_to_save)
        self.GenKeepAlive(path_to_save)
        self.GenGetTargetInfo(path_to_save)
        self.GenStop(path_to_save)
        return 1

