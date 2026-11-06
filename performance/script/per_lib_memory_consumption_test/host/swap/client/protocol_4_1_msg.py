import sys
from protocol_4_0_msg import Msg_v4_0

class Msg_v4_1(Msg_v4_0):
    def __init__(self, conf):
        super(Msg_v4_1, self).__init__(conf)
    def __del__(self):
        super(Msg_v4_1, self).__del__()
        pass
    def parse(self, print_flag = 0):
        super(Msg_v4_1, self).parse()


