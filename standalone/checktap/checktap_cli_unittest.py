import unittest
try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch

import checktap_cli



class ChecktapTests(unittest.TestCase):
    on_msg = (0xC1, 0x00, 0x00, 0x00, 0x31, 0x00, 0x00, 0x00)
    off_msg = (0xC1, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00)

    vals = [
        (0x21, 0x09, 0x0200, 0x0000, on_msg, 1000),
        (0x21, 0x09, 0x0200, 0x0000, off_msg, 1000)
    ]

    def ctrl_transfer_side_effect(*args):
        return len(args[5])

    def test_checktap_cmd_on(self):
        with patch('usb.core.find') as mock:
            instance = mock.return_value
            instance.is_kernel_driver_active.return_value = True
            instance.set_configuration.return_value = True
            instance.ctrl_transfer.side_effect = self.ctrl_transfer_side_effect

            checktap = checktap_cli.checktap()
            assert checktap.cmd("on") == True

    def test_checktap_cmd_off(self):
        with patch('usb.core.find') as mock:
            instance = mock.return_value
            instance.is_kernel_driver_active.return_value = True
            instance.set_configuration.return_value = True
            instance.ctrl_transfer.side_effect = self.ctrl_transfer_side_effect

            checktap = checktap_cli.checktap()
            assert checktap.cmd("off") == True

    def test_checktap_cmd_reboot(self):
        with patch('usb.core.find') as mock:
            instance = mock.return_value
            instance.is_kernel_driver_active.return_value = True
            instance.set_configuration.return_value = True
            instance.ctrl_transfer.side_effect = self.ctrl_transfer_side_effect

            checktap = checktap_cli.checktap()
            assert checktap.cmd("reboot") == True

if __name__ == '__main__':
    unittest.main()
