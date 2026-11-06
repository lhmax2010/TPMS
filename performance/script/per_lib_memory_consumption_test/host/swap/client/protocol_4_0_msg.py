import sys
from protocol_3_0_msg import Msg_v3_0

class Msg_v4_0(Msg_v3_0):
    def __init__(self, conf):
        super(Msg_v4_0, self).__init__(conf)
    def __del__(self):
        super(Msg_v4_0, self).__del__()
        pass


