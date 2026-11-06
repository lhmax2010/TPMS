import os
import sys
import logging
import subprocess
import signal
import time
import inspect
import threading
import re
# termios is used to snapshot/restore the local terminal state around the
# sdb-shell timeout kill in executeCmd_timeout (see below).
try:
    import termios
except ImportError:
    termios = None
from checktap.checktap_cli import checktap

################################################################################
# for logging
class Constants(object):
    """docstring for Constants"""

    '''
    __VERSION__ = litmus.__version__

    LITMUS_USR_SHARE_PATH = "/usr/share/litmus/"
    SMOKED_CFG_PATH = "/usr/share/litmus-smoked/"
    SMOKED_WEBHASH_PATH = SMOKED_CFG_PATH + "webhash/"
    CFG_PATH = LITMUS_USR_SHARE_PATH + "cfg/"
    LOG_PATH = os.path.curdir
    LOCKDIR = LITMUS_USR_SHARE_PATH + "lock/"
    RESULTDIR = LITMUS_USR_SHARE_PATH + "results/"
    PLUGIN_COMMON_PATH = LITMUS_USR_SHARE_PATH + "plugins/common/"
    USERNAME = "root"
    '''

    loggingFormat = "%(asctime)s - %(levelname)s - %(filename)s - "\
                    "%(lineno)s - %(message)s"

loggingFormat = "%(asctime)s - %(levelname)s - %(filename)s - "\
                "%(lineno)s - %(message)s"
def initLogging(fname=os.path.join(os.path.curdir, "log.log")):
    """docstring for _initLogging"""
    '''
    if not os.path.exists(Constants.LOG_PATH):
        os.mkdir(Constants.LOG_PATH)
    '''
    logging.basicConfig(filename=fname, level=logging.DEBUG,
                        format=Constants.loggingFormat)

    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(logging.Formatter(Constants.loggingFormat))
    logging.getLogger().addHandler(streamHandler)


################################################################################
# for color logging

code = {'reset': '0', 'bold': '1', 'faint': '2', 'italic': '3', 'underline': '4'}
ground = {'fore': '3', 'back': '4'}
color = {'black': '0', 'red': '1', 'green': '2', 'yellow': '3', 'blue': '4', 'magenta': '5', 'cyan': '6', 'white': '7'}

def coded(v):
    return '\033[' + v + 'm'

def coded_str(string, **kwargs):
    s = ""
    for k in code.keys():
        if k in kwargs and kwargs[k] == True:
            s += coded(code[k])

    for g in ground.keys():
        if g in kwargs:
            s += coded(ground[g] + color[kwargs[g]])

    return s + string + coded(code['reset'])

def set_color(**kwargs):
    s = ""
    for k in code.keys():
        if k in kwargs and kwargs[k] == True:
            s += coded(code[k])
    for g in ground.keys():
        if g in kwargs:
            s += coded(ground[g] + color[kwargs[g]])
    print(s + "\n")

def clear_color():
    print(coded(code['reset']) + "\n")

#remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
################################################################################
# for execution cmd in device

class device(object):
    _CMD = "sdb"
    def __init__(self, *args, **kwargs):
        self._dev_serial = kwargs['dev_serial']
        # TCP-attached target (e.g. TV over sdb-TCP): the serial itself is
        # "<ip>:<port>". Unlike USB, such a device is forgotten after
        # "sdb kill-server" and never re-enumerates by itself, so it must
        # be reconnected explicitly with "sdb connect <serial>".
        self._is_tcp = ':' in str(self._dev_serial)

    def root_on(self):
        """docstring for root_on"""
        os.system("{} -s {} root on".format(self._CMD, self._dev_serial))

    def get_serial(self):
        """get the serial number of the target device"""
        return str(self._dev_serial)

    def transfer_result(self, direction, src, dest, timeout=300):
        """Bounded push/pull with exit status; legacy transfer API unchanged."""
        if direction not in ('push', 'pull'):
            raise ValueError('invalid transfer direction')
        command = [self._CMD, '-s', self._dev_serial, direction, src, dest]
        started = time.time()
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
        return dict(command=command, returncode=proc.returncode if not timed_out else None,
                    timed_out=timed_out, stdout=out.decode(errors='replace'),
                    stderr=err.decode(errors='replace'), started_at=started, ended_at=time.time())

    def executeCmd_result(self, cmd, timeout):
        """Checked target rc plus transport evidence; opt-in callers only."""
        import shlex
        import uuid
        marker = "TPMS_RC_" + uuid.uuid4().hex
        wrapped = "bash -c " + shlex.quote(cmd) + "; rc=$?; printf '\n" + marker + ":%s\n' " + '"$rc"'
        started = time.time()
        proc = subprocess.Popen([self._CMD, "-s", self._dev_serial, "shell", wrapped],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                out, err = proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                out, err = proc.communicate()
        stdout = out.decode(errors='replace')
        matches = re.findall(r"(?:^|[\r\n])" + marker + r":(\d+)\s*$", stdout)
        rc = int(matches[-1]) if matches and not timed_out and proc.returncode == 0 else None
        # Keep the transport evidence intact, but do not expose our control
        # trailer as command data. Remove exactly its injected separator too;
        # an existing command newline (or marker-like payload) must survive.
        raw_stdout = stdout
        stdout = stdout.replace('\r\n', '\n')
        stdout = re.sub(r"(?:^|\n)" + re.escape(marker) + r":\d+\s*$", "", stdout)
        return dict(command=cmd, returncode=rc, transport_returncode=proc.returncode,
                    timed_out=timed_out, stdout=stdout, raw_stdout=raw_stdout,
                    stderr=err.decode(errors='replace'),
                    started_at=started, ended_at=time.time())

    def executeCmd_timeout(self, cmd, timeout):
        """docstring for executeCmd_timeout"""
        timeout = int(timeout)
        testcmd = [self._CMD, "-s", self._dev_serial, "shell", cmd]

        # sdb puts a tty stdin into raw mode and restores it only on a clean
        # exit; if the timeout path below SIGTERMs sdb mid-command, the
        # restore never runs and the caller's terminal stays raw (echo off),
        # so the terminal looks dead after TPMS.sh finishes. Feed sdb
        # /dev/null as stdin so it never touches the tty, and snapshot the
        # termios to restore defensively on the kill path.
        saved_termios = None
        if termios is not None:
            try:
                if os.isatty(0):
                    saved_termios = termios.tcgetattr(0)
            except Exception:
                saved_termios = None
        p1 = subprocess.Popen(testcmd, stdin=subprocess.DEVNULL)

        while timeout > 0:
            if p1.poll() is not None:
                break
            time.sleep(1)
            timeout -= 1

        if timeout == 0 and p1.poll() is None:
            os.kill(p1.pid, signal.SIGTERM)
            logging.debug("timeout kill {}".format(p1.pid))
            p1.wait()  # reap the killed sdb client, avoid a zombie
            if saved_termios is not None:
                try:
                    termios.tcsetattr(0, termios.TCSANOW, saved_termios)
                except Exception:
                    pass

        return timeout

    def pushFile(self, src, dest):
        """docstring for pushFile"""

        testcmd = [self._CMD, "-s", self._dev_serial, "push", src, dest]
        logging.debug(testcmd)
        p = subprocess.Popen(testcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = p.communicate()
        __stdout = __stdout.decode()
        __stderr = __stderr.decode()
        print(__stdout)

        return __stdout

    def pullFile(self, src, dest):
        """docstring for pullFile"""
        testcmd = [self._CMD, "-s", self._dev_serial, "pull", src, dest]
        logging.debug(testcmd)
        p = subprocess.Popen(testcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = p.communicate()
        __stdout = __stdout.decode()
        __stderr = __stderr.decode()
        print(__stdout)

        return __stdout

    def kill_server(self):
        """docstring for kill_server"""
        logging.debug("{}".format(inspect.stack()[0][3]))
        timeout = 10
        __stdout = __stderr = None

        kill_proc = lambda p: p.kill()

        testcmd = ["sdb", "kill-server"]
        sp = subprocess.Popen(testcmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        kill_timer = threading.Timer(timeout, kill_proc, [sp])

        try:
            kill_timer.start()
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

        finally:
            kill_timer.cancel()
            kill_timer.join()

        return __stdout

    def _reconnect_tcp(self):
        """Reconnect a TCP-attached device; no-op for USB serials.

        A device attached over sdb-TCP (e.g. TV target) does not survive
        "sdb kill-server" and is not re-enumerated automatically after
        reboot, so the host must re-issue "sdb connect <serial>".
        Calling connect on an already-connected serial is cheap and safe.
        """
        if not self._is_tcp:
            return
        # Bound each attempt: during target boot, "sdb connect" can block
        # for tens of seconds on a half-open handshake, which would eat the
        # whole reboot retry budget. The retry loop re-issues connect.
        os.system("timeout -k 2 15 {} connect {}".format(self._CMD, self._dev_serial))
    def refresh_tcp_connection(self):
        """Drop and re-establish the TCP transport; no-op for USB serials.

        "sdb connect" is a no-op when the serial is already listed, even if
        the underlying transport went stale: during target boot the attach
        can succeed before the device finishes going down (or before sdbd
        settles), and the half-dead link only fails later with "closed".
        Call this after a post-reboot wait, before running test commands.
        """
        if not self._is_tcp:
            return
        # Warm-up probe: on the TV image sdbd.service is socket-activated and
        # stops when idle; "sdb connect" only re-attaches the host side and
        # does NOT wake the service, so the first real shell exec on a fresh
        # or long-idle attach returns "closed". Probe with a trivial command
        # (failure tolerated) until the exec channel is confirmed warm.
        probe = [self._CMD, "-s", self._dev_serial, "shell", "echo __tpms_probe__"]
        # ASAN TV image: under boot load (load avg 40+) a simple echo probe
        # can take >90s; 3x90s was observed to exhaust and leave the serial
        # detached ("target not found"). Bump to 4 attempts x 150s.
        for attempt in range(4):
            os.system("timeout -k 2 15 {} disconnect {}".format(self._CMD, self._dev_serial))
            os.system("timeout -k 2 15 {} connect {}".format(self._CMD, self._dev_serial))
            try:
                sp = subprocess.Popen(probe, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                __out, _ = sp.communicate(timeout=150)
                if b"__tpms_probe__" in __out:
                    return
            except Exception:
                pass
        logging.debug("refresh_tcp_connection: probe failed after 4 attempts")

    def start_server(self):
        """docstring for start_server"""
        logging.debug("{}".format(inspect.stack()[0][3]))
        timeout = 10
        __stdout = __stderr = None

        start_proc = lambda p: p.kill()

        testcmd = ["sdb", "start-server"]
        sp = subprocess.Popen(testcmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        kill_timer = threading.Timer(timeout, start_proc, [sp])

        try:
            kill_timer.start()
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
        finally:
            kill_timer.cancel()
            kill_timer.join()

        # TCP target: a freshly started sdb server forgets all TCP
        # connections, so re-issue "sdb connect" immediately.
        self._reconnect_tcp()

        return __stdout

    def get_device_list(self):
        """docstring for get_device_list"""
        logging.debug("{}".format(inspect.stack()[0][3]))
        timeout = 10
        __stdout = __stderr = None
        kill_proc = lambda p: p.kill()

        testcmd = [self._CMD, "devices"]
        sp = subprocess.Popen(testcmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        kill_timer = threading.Timer(timeout, kill_proc, [sp])

        try:
            kill_timer.start()
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
        finally:
            kill_timer.cancel()
            kill_timer.join()

        return __stdout

    def remount_rootfs_rw(self):
        timeout = 10
        cmd = "mount -o remount,rw /"
        self.executeCmd_timeout(cmd, timeout)

    def _is_freshly_booted(self, since):
        """True if the target's uptime < wall time elapsed since `since`.

        Proves a reboot really happened: a slow-shutdown TCP target (e.g.
        ASAN build) can be re-attached BEFORE it ever went down, and that
        stale attach passes the naive "serial listed as device" check.
        After a real reboot, uptime < (now - reboot_request_time) always
        holds; for a stale attach, uptime vastly exceeds it.
        """
        try:
            sp = subprocess.Popen([self._CMD, "-s", self._dev_serial,
                                   "shell", "cat", "/proc/uptime"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            out, _ = sp.communicate(timeout=90)
            uptime = float(out.decode().split()[0])
            elapsed = time.time() - since
            # Grace margin: reboot_ts is stamped when the reboot command
            # returns, but the kernel already restarted during the command
            # flight (~1-2s), so a healthy fast-rebooting target shows
            # uptime == elapsed + ~2s. Stale attaches exceed elapsed by the
            # whole previous session uptime (minutes+), so 60s is safe.
            fresh = uptime < elapsed + 60
            logging.debug("target uptime {:.0f}s vs {:.0f}s since reboot request -> fresh={}".format(uptime, elapsed, fresh))
            return fresh
        except Exception as e:
            logging.debug("_is_freshly_booted probe failed: {}".format(e))
            return False

    def reboot_device_cmd(self, cmd):
        """docstring for reboot_device"""
        result = True
        # 20s is too short for the reboot exec itself on a loaded ASAN
        # target (a bare "echo" probe took 48s under boot load); the
        # exec then times out before the device even starts going down.
        test_timeout = 120

        try:
            # Warm the exec channel (disconnect+connect+probe) right before
            # issuing reboot; on a long-idle TCP attach the first exec can
            # hang or return "closed" and the reboot command would be lost.
            self.refresh_tcp_connection()
            remained_time = self.executeCmd_timeout(cmd, test_timeout)

            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                raise Exception("fail to reboot")

            # Reference point for _is_freshly_booted(): uptime measured after
            # this moment must be smaller than the elapsed wall time.
            reboot_ts = time.time()
            time.sleep(20)

            retry = 30
            ready = False
            # Counts consecutive stale attaches; used to detect a lost reboot
            # command and re-issue it.
            stale_count = 0
            while retry > 0:
                os.system("sudo -n udevadm trigger")

                # TCP target: re-issue "sdb connect" while waiting for the
                # device to boot, because the connection is not restored
                # automatically. No-op for USB serials.
                self._reconnect_tcp()

                __list = self.get_device_list()
                logging.debug("\n{}".format(__list))

                for l in __list.split("\n"):
                    __dev_info = re.split(r'[ \t]+', l.strip())
                    if __dev_info[0] == self._dev_serial:
                        if __dev_info[1] == 'device':
                            # TCP: reject a stale attach from before the actual
                            # shutdown. If the device is clearly up but the
                            # reboot never happens (command lost on a flapping
                            # channel), re-warm and re-issue the reboot.
                            # Time-based threshold avoids double-rebooting a
                            # slow-shutdown target.
                            if self._is_tcp and not self._is_freshly_booted(reboot_ts):
                                stale_count += 1
                                logging.debug("stale attach #{} (target not rebooted yet); disconnect and keep waiting".format(stale_count))
                                os.system("timeout -k 2 15 {} disconnect {}".format(self._CMD, self._dev_serial))
                                if stale_count >= 2 and (time.time() - reboot_ts) > 90:
                                    logging.debug("reboot command seems lost; re-warm channel and re-issue")
                                    stale_count = 0
                                    self.refresh_tcp_connection()
                                    self.executeCmd_timeout(cmd, test_timeout)
                                    reboot_ts = time.time()
                                break
                            ready = True
                            break

                if ready:
                    self.root_on()
                    self.remount_rootfs_rw()
                    break

                if retry % 10 == 0:
                    self.kill_server()
                    time.sleep(5)
                    self.start_server()

                time.sleep(5)
                retry -= 1

            if retry == 0:
                logging.debug("reboot command failed, let's perform checktap reset")
                _checktap = checktap()
                if _checktap.dev_error is False:
                    if _checktap.cmd("reboot") is False:
                        err = _checktap.get_err_msg()
                        raise Exception("fail to reboot(device unstable) " + err)

                    time.sleep(120)

                    ready = False;
                    for l in __list.split("\n"):
                        __dev_info = re.split(r'[ \t]+', l.strip())
                        if __dev_info[0] == self._dev_serial:
                            if __dev_info[1] == 'device':
                                ready = True
                                break
                    if ready:
                        self.root_on()
                        self.remount_rootfs_rw()
                    else:
                        result = False

                else:
                    err = _checktap.get_err_msg()
                    raise Exception("fail to reboot(device unstable) " + err)

        except Exception as err:
            logging.debug(err)
            result = False

        return result

    def reboot_device(self):
        """docstring for reboot_device"""
        return self.reboot_device_cmd("reboot")

    def reboot_device_download(self):
        """docstring for reboot_device_download"""
        retry = 5
        result = False

        while retry > 0:
       	    result = reboot_device_cmd("reboot download")
            if result == False:
                retry -= 1
            else:
                break
        return result
