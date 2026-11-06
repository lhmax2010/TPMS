import sys
import protocol_0_0_msg
from protocol_0_0_msg import Msg_v0_0

class Msg_v3_0(Msg_v0_0):
    def __init__(self, conf):
        super(Msg_v3_0, self).__init__(conf)
    def __del__(self):
        super(Msg_v3_0, self).__del__()
        pass
    def parse(self, print_flags = 0):
        super(Msg_v3_0, self).parse(print_flags)

