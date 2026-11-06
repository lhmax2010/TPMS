import time
import sys
import usb

idVendor = 0x2407
idProduct = 0x3004
on_msg = [0xC1, 0x00, 0x00, 0x00, 0x31, 0x00, 0x00, 0x00]
off_msg = [0xC1, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00]


class checktap(object):
    err_msg = ""
    MULTI_TRIES = 5
    DELAY = 1.0

    def __init__(self):
        self.dev = usb.core.find(idVendor=idVendor, idProduct=idProduct)

        if not self.dev:
            self.dev_error = True
            self.err_msg = "No checktap device found"
        else:
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)

            self.dev_error = True
            self.err_msg = "Configuration set failed"
            for i in range(self.MULTI_TRIES):
                try:
                    self.dev.set_configuration()
                    self.dev_error = False
                    self.err_msg = ""
                    break
                except Exception as e:
                    print("Failed {}th trial ({})".format(i, e))
                time.sleep(self.DELAY)

    def cmd(self, op):
        if op == "on":
            return self._checktap_on()
        elif op == "off":
            return self._checktap_off()
        elif op == "reboot":
            return self._checktap_reboot()

    def get_err_msg(self):
        return self.err_msg

    def _checktap_reboot(self):
        if self._checktap_off() == True:
            time.sleep(self.DELAY)
            return self._checktap_on()
        self.err_msg = "Operation failed"
        return False

    def _checktap_on(self):
        if self.dev_error:
            return False
        return self._checktap_on_multitries()

    def _checktap_off(self):
        if self.dev_error:
            return False
        return self._checktap_off_multitries()

    def _checktap_on_multitries(self):
        for i in range(self.MULTI_TRIES):
            if self._send_msg(on_msg) == True:
                return True
        return False

    def _checktap_off_multitries(self):
        for i in range(self.MULTI_TRIES):
            if self._send_msg(off_msg) == True:
                return True
        return False

    def _send_msg(self, msg):
        ret = self.dev.ctrl_transfer(0x21, 0x09, 0x0200, 0x0000, msg, 1000)
        if ret == len(msg):
            return True
        time.sleep(self.DELAY)
        return False


if __name__ == "__main__":
    if sys.argv.__len__() < 2:
        print("Operation argument should be given: on, off, reboot")
        sys.exit(-1)
    op = sys.argv[1]
    check = checktap()
    if check.dev_error:
        print(check.get_err_msg())
        sys.exit(-1)
    msg = check.cmd(op)
    if check.dev_error:
        print("Error: " + check.get_err_msg())
