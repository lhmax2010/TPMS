import os
import sys
import time
import shutil
import logging
import subprocess
import inspect
import re
import json
import traceback
import signal

import argparse
import configparser
from collections import OrderedDict

from tpms_util import initLogging
from tpms_util import coded_str
from tpms_util import device

from pprint import pp

class TestPerformance():
    target_exe_path = "/opt/usr/tpms/bin"
    target_out_path = "/opt/usr/tpms/result"
    target_input_path = "/opt/usr/tpms/file"

    host_result_path = None
    host_extra_result_path = None
    report_file = None
    report_ver = "0.1"
    profile_name = None
    _testinfo = dict()
    _snapshot_id = "now_testing"
    save_target_images = False

    def __init__(self, *args, **kwargs):
        self._testinfo['test_profile_data'] = kwargs['config']
        self.output_root = kwargs['output_path']
        self._device = kwargs['device']
        self.profile_name = self._testinfo['test_profile_data']['name']

        '''
        performance test list
        '''
        self.performance_test_list = [
                     {'name': 'wait_for_stability', 'func':self.wait_for_stability},
                     {'name': 'build_info_test', 'func':self.run_build_info_test},
                     {'name': 'booting_time_test', 'func':self.run_booting_time_test},
                     {'name': 'memory_usage_test', 'func':self.run_memory_usage_test},
                     {'name': 'nand_usage_test', 'func':self.run_nand_usage_test},
                     {'name': 'rootfs_usage_test', 'func':self.run_rootfs_usage_test},
                     {'name': 'app_launching_test', 'func':self.run_app_launching_test},
                     {'name': 'web_app_launching_test', 'func':self.run_web_app_launching_test},
                     {'name': 'dali_3d_ui_test', 'func':self.run_dali_3d_ui_test},
                     {'name': 'glbench_test', 'func':self.run_glbench_test},
                     {'name': 'octane_test', 'func':self.run_octane_test},
                     {'name': 'delim_info', 'func':self.append_delim},
                     {'name': 'process_memory_usage_test', 'func':self.run_process_memory_usage_test},
                     {'name': 'memory_info_test', 'func':self.run_memory_info_test},
                     {'name': 'dependency_info_test', 'func':self.run_dependency_info_test},
                     {'name': 'per_lib_memory_consumption_test', 'func' : self.run_per_lib_memory_consumption},
                     {'name': 'per_lib_time_consumption_test', 'func' : self.run_per_lib_time_consumption},
                     {'name': 'efl_benchmark_test', 'func' : self.run_efl_benchmark_test},
                     {'name': 'applaunch_memstress_test', 'func' : self.run_applaunch_memstress_test},
                     {'name': 'ffmpeg_benchmark_test', 'func' : self.run_ffmpeg_benchmark_test},
                     {'name': 'gstreamer_benchmark_test', 'func' : self.run_gstreamer_benchmark_test},
                     {'name': 'tflite_benchmark_test', 'func' : self.run_tflite_benchmark_test},
                     {'name': 'kernel_benchmark_test', 'func' : self.run_kernel_benchmark_test},
                     {'name': 'dotnet_benchmark_test', 'func' : self.run_dotnet_benchmark_test},
                    ]

        cur_path = os.path.dirname(os.path.abspath(__file__))
        self._testinfo['test_profile_data']['tpms_cfg'] = os.path.join(cur_path, self._testinfo['test_profile_data']['tpms_cfg'])

        with open(self._testinfo['test_profile_data']['tpms_cfg'], "r") as f:
            cfg_dict = json.load(f, object_pairs_hook=OrderedDict)
            enabled = cfg_dict['enabled']
            from memory_rigor import config as memory_config
            self.memory_rigor = memory_config(cfg_dict.get("memory_rigor"))
            self._memory_runner = None

            self.script_path = os.path.join(cur_path, str(cfg_dict['script_path']))
            self.target_installable_path = os.path.join(cur_path, str(cfg_dict['target_installable_path']), self.profile_name)
            if "save_target_images" in enabled:
                self.save_target_images = True if enabled["save_target_images"] == 'enable' else False
            for t in self.performance_test_list:
                if t['name'] in enabled:
                    t['enable'] = True if enabled[t['name']] == 'enable' else False
                else:
                    t['enable'] = True

    def clear_target_data(self):
        test_timeout = 60
        cmd = "rm -rf /opt/usr/tpms && mkdir -p " + self.target_out_path + " && mkdir -p " + self.target_input_path
        remained_time = self._device.executeCmd_timeout(cmd, test_timeout)


    def _target_script_cmd(self, test_name, target_exe_name, args):
        """Build an sdb-shell command that runs a target test script.

        Samsung TV targets enforce UEP (Unsigned Execution Prevention): a
        patched bash refuses to execute unsigned script FILES
        ("[uep][bash] the file is NOT signed!!"). Piping the script content
        through stdin bypasses the signature check; TPMS_TEST_NAME carries
        the real test name because $0 becomes "bash" in this mode.
        """
        script = os.path.join(self.target_exe_path, target_exe_name)
        return "cat {} | TPMS_TEST_NAME={} TPMS_SCRIPT_DIR={} bash -s -- {}".format(
            script, test_name, self.target_exe_path, args)

    def setup_test_env(self):
        """docstring for setup_test_env"""
        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))
        ret = True
        try:
            '''
            check result directory
            '''
            test_profile_result_path = os.path.join(self.output_root, self.profile_name)
            if not os.path.exists(test_profile_result_path):
                cmd = "mkdir -p {}".format(test_profile_result_path)
                logging.debug("creating result directory for test profile (cmd={})".format(cmd))
                os.system(cmd)
                cmd = "chmod 755 {}".format(test_profile_result_path)
                os.system(cmd)

            self.host_result_path = os.path.join(test_profile_result_path, str(self._snapshot_id))
            if os.path.exists(self.host_result_path):
                cmd = "rm -rf {}/*".format(self.host_result_path)
                logging.debug("remove existing result file by (cmd={})".format(cmd))
                os.system(cmd)
            else:
                cmd = "mkdir {}".format(self.host_result_path)
                logging.debug("create result dir by (cmd={})".format(cmd))
                os.system(cmd)
                cmd = "chmod 755 {}".format(self.host_result_path)
                os.system(cmd)

            self.host_extra_result_path = os.path.join(self.host_result_path, "extra")
            cmd = "mkdir {}".format(self.host_extra_result_path)
            logging.debug("create result dir by (cmd={})".format(cmd))
            os.system(cmd)
            cmd = "chmod 755 {}".format(self.host_extra_result_path)
            os.system(cmd)

            self.report_file = os.path.join(self.host_result_path, "report.txt")

        except Exception as e:
            logging.error(e)
            ret = False

        return ret


    def append_to_report(self, info):
        result = None

        try:
            with open(self.report_file, 'a') as f:
                f.writelines(info.strip() + '\n')

        except Exception as err:
            logging.error(e)
            result = None

        return result


    def append_report_ver(self):
        """docstring for append_report_ver"""
        self.append_to_report(str(dict(report_ver = self.report_ver)))


    def append_target_info(self):
        """docstring for append_target_info"""
        self.append_to_report(str(dict(target_info = self.profile_name)))


    def append_delim(self, *args, **kwargs):
        """docstring for target_info_test"""

        info = {'tag_name': 'test', 'sub_tag_list': [{'tag_name': 'executiontime', 'attrs': {'isRelevant': 'false', 'unit': 's', 'val': '-9999'}}], 'test_state': 'success', 'attrs': {'executed': 'yes', 'name': '==========================='}}
        self.append_to_report(str(info))

        return True


    def gen_perfpublisher_xml(self):
        """docstring for gen_perfpublisher_xml"""
        xml_result_file = "perfpublisher.xml"
        gen_perfpublisher_xml_exe = 'gen_perfpublisher_xml.py'
        __stdout = None
        __stderr = None

        cmd = [os.path.join(self.script_path, 'common', 'host', gen_perfpublisher_xml_exe), self.report_file, "-o", os.path.join(self.host_result_path, xml_result_file)]
        print(f"cmd: {' '.join(cmd)}")
        sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        __stdout, __stderr = sp.communicate()
        __stdout = __stdout.decode()
        __stderr = __stderr.decode()

        test_state = 'success' if sp.returncode == 0 else 'fail'

        logging.debug("{}: returncode={}\nstdout=\n{}\nstderr=\n{}"\
                   .format(inspect.stack()[0][3], sp.returncode, __stdout, __stderr))

        return sp.returncode

    def _rpm_query_installed(self, package):
        """Check `rpm -q <package>` on the device.

        Returns True (installed), False (definitely not installed), or None
        when the check itself could not run (flapping TCP exec channel,
        e.g. sdb returned "closed"/"target not found"/timeout).
        """
        try:
            sp = subprocess.Popen(["sdb", "-s", self._device._dev_serial,
                                   "shell", "rpm -q " + package],
                                  # DEVNULL stdin: keep sdb off the local tty
                                  # (raw-mode risk, see tpms_util tty fix).
                                  stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = sp.communicate(timeout=150)
            out_s = out.decode(errors="replace")
            err_s = err.decode(errors="replace")
            # [AI FIX 2026-10-15] Check "not installed" FIRST: on this TV image
            # `rpm -q <pkg>` prints "package <pkg> is not installed" with exit
            # code 0, and that message itself contains <pkg>, so a positive
            # substring match alone falsely reports "installed".
            if "not installed" in out_s or "not installed" in err_s:
                return False
            if sp.returncode == 0 and package in out_s:
                return True
            return None
        except Exception:
            return None

    def _rpm_install_marker_ok(self, marker_file):
        """Pull the install marker file and return True iff it contains OK."""
        if os.path.exists("tpms_rpm_install_result"):
            os.remove("tpms_rpm_install_result")
        self._device.pullFile(marker_file, "./")
        ok = False
        if os.path.exists("tpms_rpm_install_result"):
            with open("tpms_rpm_install_result", 'r') as f:
                if "OK" in f.read():
                    ok = True
            os.remove("tpms_rpm_install_result")
        return ok

    def install_package_from_repo(self, package, allow_latest_fallback=True):
        """ download .rpm package from repo server and install to target """
        index_file = "index.html"
        test_timeout = 120

        # Pre-check with warm-up + retries: if the package is already on the
        # device, skip download+install entirely. This both saves time and
        # avoids the flapping-channel hazard for the common re-run case.
        # `None` (check could not run) falls through to a real install attempt.
        for _ in range(3):
            self._device.refresh_tcp_connection()
            r = self._rpm_query_installed(package)
            if r is True:
                logging.debug("{} already installed on device, skipping repo install".format(package))
                return True
            if r is False:
                break

        # Get file name of the package
        latest_repo = self._testinfo['test_profile_data']['repo_url']
        item = self._snapshot_id.split("_")
        # _snapshot_id can be "latest" or "now_testing" (test_only flows);
        # both lack a "_"-separated build suffix. Guard against IndexError
        # and fall back to the plain id (repo url then stays on "latest").
        snapshot_ver = item[0] + "_" + item[1] if len(item) > 1 else self._snapshot_id

        # Toolchain snapshots (e.g. tizen-unified-toolchain_YYYYMMDD.HHMMSS) are
        # published under Tizen-Unified-Toolchain / Tizen-Base-Toolchain,
        # not Tizen-Unified / Tizen-Base
        if item[0].endswith("-toolchain"):
            latest_repo = latest_repo.replace("/Tizen-Unified/", "/Tizen-Unified-Toolchain/")\
                                     .replace("/Tizen-Base/", "/Tizen-Base-Toolchain/")

        snapshot_repo = latest_repo.replace("latest", snapshot_ver)
        if not allow_latest_fallback and self._snapshot_id in ('latest', 'now_testing'):
            # Explicit configured source for a test-only image, never a failed
            # versioned request silently redirected to latest.
            snapshot_repo = latest_repo
            logging.info("memory_rigor: explicit profile repo source %s", snapshot_repo)

        snapshot_serverid = self._testinfo['test_profile_data']['snapshot_serverid']
        snapshot_serverpasswd = self._testinfo['test_profile_data']['snapshot_serverpasswd']

        # Try to get index.html of current version
        # (wget -O creates an empty index.html even on 404, so the exit code
        #  and the file size must be checked, not just the file existence)
        cmd = "wget --no-cache --user={} --password={} --no-verbose {} -O index.html".format(snapshot_serverid, snapshot_serverpasswd, snapshot_repo)
        ret = os.system(cmd)

        if ret == 0 and os.path.exists(index_file) and os.path.getsize(index_file) > 0:
            repo_url = snapshot_repo
        else:
            if not allow_latest_fallback:
                logging.error("memory_rigor: snapshot unavailable; latest fallback disabled")
                return False
            if package == 'memps' and getattr(self, 'memory_rigor', {}).get('enabled', False):
                self._memory_tool_fallback_reason = 'snapshot index unavailable/empty: ' + snapshot_repo + '; rc=' + str(ret)
            # Fall back to latest version
            cmd = "wget --no-cache --user={} --password={}  --no-verbose {} -O index.html".format(snapshot_serverid, snapshot_serverpasswd, latest_repo)
            ret = os.system(cmd)
            repo_url = latest_repo
            if ret != 0 or not os.path.exists(index_file) or os.path.getsize(index_file) == 0:
                logging.debug(coded_str("Failed to get {} from repo".format(index_file),
                                        fore='red', bold=True))
                return False

        cmd = "sed -i 's/<[^>]*>/ /g' index.html"
        os.system(cmd)

        package_file = None
        with open(index_file, 'r') as file:
            for line in file:
                if line.find(package) >= 0:
                    #package_file = line.split(" ")[0]
                    line_temp=re.sub(' +',' ',line)
                    package_file = line_temp.split(" ")[1]
                    break

        # Download the package from repo server and push to device
        os.remove(index_file)

        if not package_file:
            logging.debug(coded_str("Failed to find package {} in repo index".format(package),
                                    fore='red', bold=True))
            return False
        cmd = "wget --no-cache --user={} --password={}  --no-verbose {}{}".format(snapshot_serverid, snapshot_serverpasswd, repo_url, package_file)
        os.system(cmd)

        if not os.path.exists(package_file):
            logging.debug(coded_str("Failed to get {} from repo".format(package_file),
                                    fore='red', bold=True))
            return False

        if not allow_latest_fallback or (package == 'memps' and getattr(self, 'memory_rigor', {}).get('enabled', False)):
            self._memory_tool_url = repo_url + package_file

        # Install the package and verify it was actually installed.
        # rpm -ivh may silently fail (e.g. dependency issues with latest RPM
        # on an older snapshot), so we write a marker file to check the result.
        marker_file = "/tmp/tpms_rpm_install_result"
        cmd = "/bin/bash -c " + "\"" + "rpm -ivh --force --nodeps" + " " + \
                os.path.join(self.target_input_path, package_file) + \
                " && rpm -q " + package + " && echo OK > " + marker_file + \
                " || echo FAIL > " + marker_file + \
                " ; sync" + "\""

        # Push + install + verify with retries: on the ASAN TV image the TCP
        # exec channel can die within seconds of a successful probe, so a
        # single warm-up is not sufficient. Re-warm and retry the whole
        # push+install cycle; verify via the marker file each time.
        install_ok = False
        for attempt in range(3):
            self._device.refresh_tcp_connection()
            self._device.pushFile(package_file, self.target_input_path)
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug(coded_str("rpm install timeout for {} (attempt {})".format(
                                        package_file, attempt + 1),
                                        fore='red', bold=True))
            install_ok = self._rpm_install_marker_ok(marker_file)
            # Clean up marker file on device
            self._device.executeCmd_timeout("rm -f " + marker_file, 10)
            if install_ok:
                break
            logging.debug(coded_str("rpm install verification failed for {} (attempt {})".format(
                                    package, attempt + 1),
                                    fore='red', bold=True))

        os.remove(package_file)

        if not install_ok:
            logging.debug(coded_str("rpm install verification failed for {}".format(package),
                                    fore='red', bold=True))
            return False

        return True




    def install_package_from_localpath(self, test_name):
        """ push .rpm package from local path and install to target """
        test_timeout = 120
        """ TODO: download from the repo """
        # Use arch from testprofiles.cfg to determine RPM package architecture
        arch = self._testinfo['test_profile_data'].get('arch', '')

        # Find RPM file by pattern matching instead of hardcoded filename
        rpm_dir = os.path.join(self.target_installable_path, test_name, 'file')
        if arch in ('aarch64', 'arm64'):
            rpm_pattern = re.compile(r'^com\.samsung\.dali-demo-.*\.aarch64\.rpm$')
        else:
            rpm_pattern = re.compile(r'^com\.samsung\.dali-demo-.*\.armv7l\.rpm$')

        package_filename = None
        if os.path.isdir(rpm_dir):
            for f in os.listdir(rpm_dir):
                if rpm_pattern.match(f):
                    package_filename = f
                    break

        if not package_filename:
            logging.error(coded_str("Failed to find RPM package in {} for arch={}".format(rpm_dir, arch),
                                    fore='red', bold=True))
            return False

        src = os.path.join(rpm_dir, package_filename)
        dest = self.target_input_path
        self._device.pushFile(src, dest)

        cmd = "/bin/bash -c " + "\"" + "rpm -ivh --force --nodeps" + " " + \
                os.path.join(self.target_input_path, package_filename) + \
                " ; sync" + "\""
        remained_time = self._device.executeCmd_timeout(cmd, test_timeout)

        return True

    def install_package_local_first(self, package, test_name):
        """Install a package on the target, preferring a local RPM file.

        Looks for an RPM matching "<package>-*.rpm" in the local
        target_installable/<profile>/<test_name>/file/ directory first.
        If found, pushes and installs it with rpm --force --nodeps.
        If no local RPM exists, falls back to downloading the package
        from the snapshot repo via install_package_from_repo().

        Returns True if the package was installed (from either source),
        False otherwise.
        """
        test_timeout = 120
        rpm_dir = os.path.join(self.target_installable_path, test_name, 'file')

        # Look for a local RPM named like <package>-<version>.<arch>.rpm
        rpm_pattern = re.compile(r'^{}-.+\.rpm$'.format(re.escape(package)))
        package_filename = None
        if os.path.isdir(rpm_dir):
            for f in sorted(os.listdir(rpm_dir)):
                if rpm_pattern.match(f):
                    package_filename = f
                    break

        if package_filename:
            logging.debug(coded_str("Installing {} from local file {}".format(
                package, os.path.join(rpm_dir, package_filename)), fore='green', bold=True))

            src = os.path.join(rpm_dir, package_filename)
            self._device.pushFile(src, self.target_input_path)

            cmd = "/bin/bash -c " + "\"" + "rpm -ivh --force --nodeps" + " " + \
                    os.path.join(self.target_input_path, package_filename) + \
                    " ; sync" + "\""
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug(coded_str("rpm install timeout for local {}".format(package_filename),
                                        fore='red', bold=True))
                return False
            return True

        # No local RPM found, fall back to repo download
        logging.debug(coded_str("No local RPM for {} in {}, downloading from repo".format(
            package, rpm_dir), fore='yellow', bold=True))
        return self.install_package_from_repo(package)

    def install_packages_local_first(self, packages, test_name):
        """Install a list of packages, each one local-first with repo fallback.

        Individual package failures are logged as warnings but do not stop
        the remaining packages from being installed (same tolerance policy
        as the existing benchmark tests).

        Returns True if all packages were installed, False if any failed.
        """
        all_ok = True
        for pkg in packages:
            logging.debug("Installing package: {}".format(pkg))
            if not self.install_package_local_first(pkg, test_name):
                logging.debug(coded_str("Failed to install {} (may already be installed)".format(pkg),
                                        fore='yellow', bold=True))
                all_ok = False
        return all_ok

    def _get_memory_runner(self):
        from memory_rigor_runner import MemoryRigorRunner
        if self._memory_runner is None:
            self._memory_runner = MemoryRigorRunner(self)
        return self._memory_runner

    def wait_for_stability(self, *args, **kwargs):
        if getattr(self, "memory_rigor", {}).get("enabled", False):
            return self._get_memory_runner().standalone_gate()
        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))


    def run_build_info_test(self, *args, **kwargs):
        """docstring for run_build_info_test"""
        result = True
        wait_time = 0
        need_reboot = False
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = "info.ini"
        os_release_file = "/etc/os-release"
        post_processing_exe = "parse_build_info.py"
        __stdout = __stderr = None
        test_timeout = 60

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            #TODO: exit code handling of sdb shell command, but now sdb do not return exit code. it's always 0
            # UEP-safe: pipe script via stdin instead of executing the file
            cmd = self._target_script_cmd(test_name, target_exe_name, os.path.join(self.target_out_path, result_file))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)

            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            src = os.path.join(self.target_out_path, result_file)
            dest = self.host_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, result_file)):
                raise Exception("fail to pull test result file")

            self._device.pullFile(os_release_file, self.host_result_path)
            if self._snapshot_id == "now_testing":
                # TODO: Need to define global policy for snapshot id which can cover
                # both litmus and standalone case
                file_path = os.path.join(self.host_result_path, "os-release")
                with open(file_path, 'r') as file:
                    for line in file:
                        if line.find("BUILD_ID") >= 0:
                            self._snapshot_id = line.split("=")[1]
                            logging.debug("Set _snapshot_id : {}".format(self._snapshot_id))
                            break

            extra_result_file = "dlog_" + test_name + ".txt"
            src = os.path.join(self.target_out_path, extra_result_file)
            dest = self.host_extra_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, extra_result_file)):
                raise Exception("fail to pull extra result file")

            for f in os.listdir('./'):
                if f.endswith(".packages") | ((f.endswith(".tar.gz") & self.save_target_images)):
                    shutil.copy(f, self.host_result_path + "/")
                    logging.debug("copied packages file " + f + " to " + self.target_out_path)

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}\nreturncode={}\nstdout=\n{}\nstderr=\n{}"\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_booting_time_test(self, *args, **kwargs):
        """docstring for run_booting_time_test"""
        result = True
        need_reboot = True
        wait_time = 240
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        package_name = "systemd-analyze"
        result_file = ["systemd_plot.svg", "systemd_user_plot.svg"]
        post_processing_exe = "get_service_termination_time.py"
        __stdout = __stderr = None
        test_timeout = 240

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            if self.install_package_from_repo(package_name) == False:
                raise Exception("Failed to install {}".format(package_name))

            if need_reboot:
                reseted_time = time.time()

                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            #run test in target
            # UEP-safe: pipe script via stdin instead of executing the file
            cmd = self._target_script_cmd(test_name, target_exe_name, os.path.join(self.target_out_path, result_file[0]) + " " + os.path.join(self.target_out_path, result_file[1]))

            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            for r in result_file:
                src = os.path.join(self.target_out_path, r)
                dest = self.host_result_path + "/"
                self._device.pullFile(src, dest)

                if not os.path.exists(os.path.join(dest, r)):
                    raise Exception("fail to pull test result file")

            extra_result_file = "dlog_" + test_name + ".txt"
            src = os.path.join(self.target_out_path, extra_result_file)
            dest = self.host_extra_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, extra_result_file)):
                raise Exception("fail to pull extra result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file[0]),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result

    def run_per_lib_time_consumption(self, *args, **kwargs):
        NUMBER_OF_RUNS = 3
        pkg_list_file = "native_pkg_list.txt"
        test_name = kwargs.get('name')
        scriptsPath = os.path.join(self.script_path, test_name, 'host', 'scripts')
        sys.path.append(scriptsPath)
        import run

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        f = open(os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file), 'r')
        for line in f:
            if re.match(r'^#.*', line):
                continue

            applicationName, applicationPath= re.split(r'[ \t]+', line.strip())

            result = run.timeMeasurmentPerf(os.path.join(self.script_path, test_name),
                self._device.pushFile, self._device.executeCmd_timeout,
                self._device.executeCmd_background, self._device.executeCmd2,
                self._device.pullFile, self._device.reboot_device,
                coded_str, applicationName, applicationPath, self.host_result_path,
                self.report_file, NUMBER_OF_RUNS)

            if result == False:
                return result

        return result


    def run_per_lib_memory_consumption(self, *args, **kwargs):
        NUMBER_OF_RUNS = 3
        pkg_list_file = "native_pkg_list.txt"
        test_name = kwargs.get('name')
        scriptsPath = os.path.join(self.script_path, test_name, 'host', 'scripts')
        sys.path.append(scriptsPath)
        import run
        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        f = open(os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file), 'r')
        for line in f:
            if re.match(r'^#.*', line):
                continue

            applicationName, applicationPath, max_tracing_time = re.split(r'[ \t]+', line.strip())

            result = run.memoryMeasurmentSwap(os.path.join(self.script_path, test_name),
                self._device.pushFile, self._device.executeCmd_timeout,
                self._device.executeCmd_background, self._device.executeCmd2,
                self._device.pullFile, self._device.reboot_device,
                coded_str, applicationName, applicationPath, self.host_result_path,
                self.report_file, NUMBER_OF_RUNS, int(max_tracing_time))

            if result == False:
                return result

        return result

    def run_efl_benchmark_test(self, *args, **kwargs):
        result = True
        #need_reboot = True
        #wait_time = 240
        post_processing_exe = "get_efl_bench_result.py"
        result_file = "efl_bench_result.txt"
        test_name = kwargs.get('name')
        scriptsPath = os.path.join(self.script_path, test_name, 'host')
        sys.path.append(scriptsPath)
        rpm_dir=os.path.join(self.target_installable_path, test_name, 'file')

        import get_efl_benchmark_data as efl_bench

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))
        logging.debug("install efl-bench rpm from " + rpm_dir)

        try:
            result = efl_bench.do_benchmark(mode=1, rpm_dir=rpm_dir, script_dir = scriptsPath, result_dir = self.host_extra_result_path, serial = self._device.get_serial())
            if result is False:
                logging.debug("error occurred while testing efl_benchmark")
        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False
        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_extra_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))
        return result

    def run_applaunch_download_bin(self, script_home, binfile):
        tries = 0
        result = True
        #timeout = 120
        download_cmd = [os.path.join(script_home, "download.sh"), binfile]
        while tries < 5:
            sp = subprocess.Popen(download_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                __stdout, __stderr = sp.communicate()
                __stdout = __stdout.decode()
                __stderr = __stderr.decode()

            except Exception as err:
                traceback.print_exc()
                logging.debug(err)
                result = False
            finally:
                __stdout.rstrip()
                if "SUCCESS" in __stdout:
                    logging.debug("Download completed successfully")
                    result = True
                    break
                else:
                    sp.kill()
                    logging.debug("timeout kill {}".format(sp.pid))
                    tries += 1
                    if self._device.reboot_device() is False:
                        raise Exception("Failed to reboot device")
        return result

    def pull_file_multi_tries(self, src, dst):
        tries = 0
        ret = False
        while tries < 5:
            result = self._device.pullFile(src, dst)
            if "error" in result:
                logging.debug(result)
                tries += 1
                time.sleep(5)
                ret = False
            ret = True
            break
        return ret

    def push_file_multi_tries(self, src, dst):
        tries = 0
        ret = False
        while tries < 5:
            result = self._device.pushFile(src, dst)
            if "error" in result:
                logging.debug(result)
                tries += 1
                time.sleep(5)
                ret = False
            ret = True
            break
        return ret

    def run_applaunch_memstress_test(self, *args, **kwargs):
        result = True
        #need_reboot = True
        #wait_time = 300
        test_name = kwargs.get('name')
        result_file = "applaunch_memstress_result.txt"
        post_processing_exe = "get_applaunch_memstress_result.py"
        push_files = ["run.sh", "scenario.txt", "app_list.txt"]
        script_home = os.path.join(self.script_path, test_name, "host")

        test_bin = "rpi4_1gb_mem_uboot_64bit.tar"
        restore_bin = "rpi4_4gb_mem_uboot_64bit.tar"

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            logging.debug(script_home)
            if self.run_applaunch_download_bin(script_home, test_bin) is False:
                raise Exception("Failed to download image")

            time.sleep(120)
            self._device.root_on()
            self._device.remount_rootfs_rw()

            if self.pull_file_multi_tries("/etc/resourced/memory.conf", os.path.join(script_home, "memory.conf.bak")) is False:
                raise Exception("Backup failed")

            if self.push_file_multi_tries(os.path.join(script_home, "memory.conf"), "/etc/resourced/") is False:
                raise Exception("Push files failed")

            for f in push_files:
                if self._device.pushFile(os.path.join(script_home, f), "/root/") is False:
                    raise Exception("Push " + f + " is failed")

            self._device.executeCmd_timeout("sync", 10)

            if self._device.reboot_device() is False:
                raise Exception("Failed to reboot device")

            time.sleep(10)
            self._device.root_on()
            self._device.remount_rootfs_rw()
            sp_cmd = [os.path.join(script_home, "applaunch_memstress_test.sh"), self.host_extra_result_path]
            test_result = subprocess.call(sp_cmd)

            logging.debug("After test, before restore")

            if self.run_applaunch_download_bin(script_home, restore_bin) is False:
                raise Exception("Failed to restore bootloader")

            time.sleep(120)
            self._device.root_on()

            if self.push_file_multi_tries(os.path.join(script_home, "memory.conf.bak"), "/etc/resourced/memory.conf") is False:
                raise Exception("Push files failed")
        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False
        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_extra_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))
        return result


    def run_memory_usage_test(self, *args, **kwargs):
        """docstring for run_memory_usage_test"""
        if getattr(self, "memory_rigor", {}).get("enabled", False):
            runner = self._get_memory_runner()
            collected = runner.collect()
            exported = runner.export_legacy("memory_usage_test")
            ok = collected and exported
            from datetime import datetime
            print("已结束", datetime.now().astimezone().isoformat(), "状态", "成功" if ok else "失败")
            return ok


        '''
        Actually, 'memoryinfo.txt' and 'vmallocinfo.txt' are not results of this test.
        To get consistent result of others test, these files are obtained this test.
        '''

        result = True
        need_reboot = True
        wait_time = 300
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = "memps.txt"
        ion_shrink_result_file = "memps_ion_shrink.txt"
        result_files = ["memps.txt" , "meminfo.txt", "vmallocinfo.txt", ion_shrink_result_file]
        post_processing_exe = "get_used_memory.py"
        __stdout = __stderr = None
        test_timeout = 60
        test_ion_shrink_memory = True

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            # memps is absent from the TV image (it ships vd_memps instead,
            # which provides no "memps" binary); install from the snapshot
            # repo the same way booting_time installs systemd-analyze.
            if self.install_package_from_repo("memps") == False:
                raise Exception("Failed to install memps")

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            #run test in target
            cmd_args = ""
            for f in result_files:
                cmd_args += os.path.join(self.target_out_path, f) + " "

            # UEP-safe: pipe script via stdin instead of executing the file
            cmd = self._target_script_cmd(test_name, target_exe_name, cmd_args)
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            dest = self.host_result_path + "/"
            for f in result_files:
                src = os.path.join(self.target_out_path, f)
                self._device.pullFile(src, dest)
                time.sleep(2)

            for f in result_files:
                if not os.path.exists(os.path.join(dest, f)):
                    if f == ion_shrink_result_file:
                        test_ion_shrink_memory = False
                    else:
                        raise Exception("fail to pull test result file")

            extra_result_file = "dlog_" + test_name + ".txt"
            src = os.path.join(self.target_out_path, extra_result_file)
            dest = self.host_extra_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, extra_result_file)):
                raise Exception("fail to pull extra result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]

            if test_ion_shrink_memory:
                cmd += ['-s', os.path.join(self.host_result_path, ion_shrink_result_file)]

            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_nand_usage_test(self, *args, **kwargs):
        """docstring for run_nand_usage_test"""

        result = True
        need_reboot = False
        wait_time = 0
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = "rpm_qai.txt"
        post_processing_exe = "get_nand_usage.py"
        __stdout = __stderr = None
        test_timeout = 60

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            #run test in target
            # UEP-safe: pipe script via stdin instead of executing the file
            cmd = self._target_script_cmd(test_name, target_exe_name, os.path.join(self.target_out_path, result_file))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            src = os.path.join(self.target_out_path, result_file)
            dest = self.host_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, result_file)):
                raise Exception("fail to pull test result file")

            extra_result_file = "dlog_" + test_name + ".txt"
            src = os.path.join(self.target_out_path, extra_result_file)
            dest = self.host_extra_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, extra_result_file)):
                raise Exception("fail to pull extra result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_rootfs_usage_test(self, *args, **kwargs):
        """docstring for run_rootfs_usage_test"""

        result = True
        need_reboot = False
        wait_time = 0
        test_name = kwargs.get('name')
        post_processing_exe = "get_nand_usage.py"
        __stdout = __stderr = None
        test_timeout = 60
        workspace_path=self.output_root
        dir_name = os.path.join(workspace_path, 'rootfs')

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            platform_img = None
            # IGNORECASE: kantsu2e TV images are named "TIZEN-ONEMAIN-..."
            # while snapshotid_pattern starts with lowercase "tizen".
            pattern_r = re.compile(self._testinfo['test_profile_data']['snapshotid_pattern'], re.IGNORECASE)
            postfix_r = re.compile('.*.tar.gz')
            for f in os.listdir(workspace_path):
                logging.debug("file name : {}".format(f))
                m1 = pattern_r.search(f)
                m2 = postfix_r.match(f)
                m3 = re.search(r'(?<=boot)-', f)
                if m1 and m2 and not m3:
                    platform_img = os.path.join(workspace_path, f)
                    break

            print(platform_img)
            val = 0
            mounted = False

            # TV (kantsu2e) fallback: the TV platform image packs rootfs as a
            # GPT disk with an EROFS partition (pltf_t.img). EROFS cannot be
            # read without erofs-utils and interactive sudo is unavailable,
            # so read the usage from the device instead — the same EROFS is
            # mounted at /.org_rootfs and `df` reports KB used.
            def _rootfs_usage_from_device():
                try:
                    sp_cmd = [self._device._CMD, '-s', self._device._dev_serial,
                              'shell', 'df /.org_rootfs | tail -1']
                    sp = subprocess.Popen(sp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    __out, __err = sp.communicate(timeout=30)
                    __out = __out.decode()
                    m = re.search(r'\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+%\s+\S+', __out)
                    if m:
                        logging.debug("rootfs usage from device df: {}".format(__out.strip()))
                        return round(float(m.group(2)) / 1024, 1)  # Used KB -> MB
                except Exception as e:
                    logging.debug("rootfs df fallback failed: {}".format(e))
                return 0

            def _tar_has_rootfs_img(pkg):
                try:
                    sp = subprocess.Popen(['tar', 'tzf', pkg], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    __out, _ = sp.communicate(timeout=120)
                    return 'rootfs.img' in __out.decode()
                except Exception:
                    return False

            if platform_img and not _tar_has_rootfs_img(platform_img):
                # TV image: no mountable rootfs.img inside, use on-device df
                val = _rootfs_usage_from_device()
                platform_img = None  # skip the mount path below

            if platform_img:
                rootfs_img = os.path.join(workspace_path, 'rootfs.img')
                sp_cmd = ['mkdir', dir_name]
                sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                __stdout, __stderr = sp.communicate()
                __stdout = __stdout.decode()
                __stderr = __stderr.decode()
                if sp.returncode != 0:
                    raise Exception('fail to create folder {}'.format(__stderr))

                sp_cmd = ['tar', 'xzvf', platform_img, '-C', workspace_path]
                sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                __stdout, __stderr = sp.communicate()
                __stdout = __stdout.decode()
                __stderr = __stderr.decode()

                if sp.returncode != 0:
                    raise Exception('fail to extract {}'.format(__stderr))

                # sudo -n: never block on a password prompt (headless runs
                # would otherwise hang forever in communicate()).
                sp_cmd = ['sudo', '-n', 'mount', rootfs_img, dir_name]
                sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                __stdout, __stderr = sp.communicate()
                __stdout = __stdout.decode()
                __stderr = __stderr.decode()

                if sp.returncode != 0:
                    raise Exception('fail to mount {}'.format(__stderr))
                mounted = True


                cmd = ['sudo', '-n', 'du', '--max-depth=1', dir_name ]
                sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                __stdout, __stderr = sp.communicate()
                __stdout = __stdout.decode()
                __stderr = __stderr.decode()

                if sp.returncode != 0:
                    raise Exception('fail to get rootfs size {}'.format(__stderr))

                logging.debug(coded_str("{}".format(__stdout), fore='magenta'))

                r = re.compile('(?P<val>[0-9]+)[ \t]+.*{}$'.format(dir_name))
                for l in __stdout.split('\n'):
                    m = r.match(l.strip())
                    if m:
                        val = round(float(m.group('val'))/1024, 1)

            # No usable image (or the TV branch above already filled `val`
            # from the device): fall back to the on-device df so the metric
            # is still produced. Report whenever we have a positive value,
            # regardless of which path produced it.
            if val == 0:
                val = _rootfs_usage_from_device()
            if val > 0:
                info = {'tag_name': 'test',\
                        'sub_tag_list': [{'tag_name': 'performance',\
                                          'attrs': {'isRelevant': 'true', 'unit': 'MB', 'val': str(val)}}],\
                        'test_state': 'success',\
                        'attrs': {'executed': 'yes', 'name': 'RootFS Size'}}

                logging.debug(coded_str("{}".format(str(info)), fore='green'))
                self.append_to_report(str(info))

        except Exception as err:
            traceback.print_exc()
            logging.error(get_exception_info())
            result = False

        finally:
            if mounted:
                cmd = ['sudo', 'umount', dir_name ]
                sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                __stdout, __stderr = sp.communicate()
                __stdout = __stdout.decode()
                __stderr = __stderr.decode()

#                if sp.returncode != 0:
#                    raise Exception('fail to umount {}'.format(__stderr))

        return result


    def run_app_launching_test(self, *args, **kwargs):
        """docstring for run_app_launching_test"""
        result = True
        need_reboot = True
        wait_time = 100
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = ""
        pkg_list_file = "native_pkg_list.txt"
        post_processing_exe = "get_app_launching_time.py"
        __stdout = __stderr = None
        test_timeout = 1200

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            src = os.path.join(self.target_installable_path, test_name, 'file')
            dest = self.target_input_path
            self._device.pushFile(src, dest)

            src = os.path.join(self.target_installable_path, test_name, 'bin')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            # UEP bypass: pipe script through stdin instead of direct execution
            cmd = self._target_script_cmd(test_name, target_exe_name,
                  "install {} {}".format(
                  os.path.join(self.target_input_path, pkg_list_file),
                  self.target_out_path))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # UEP bypass: pipe script through stdin instead of direct execution
            cmd = self._target_script_cmd(test_name, target_exe_name,
                  "run {} {}".format(
                  os.path.join(self.target_input_path, pkg_list_file),
                  self.target_out_path))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            with open(os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file), 'r') as f:
                for line in f:
                    try:
                        if re.match(r'^#.*', line):
                            continue

                        pkg_name, pkg_file = re.split(r'[ \t]+', line.strip())[0:2]
                        for seq in ['1st', '2nd']:
                            result_file = "dlog_" + seq + "_launch_" + pkg_name + ".txt"
                            src = os.path.join(self.target_out_path, result_file)
                            dest = self.host_result_path + "/"
                            self._device.pullFile(src, dest)

                        result_file = "memps_"+pkg_name+".txt"
                        src = os.path.join(self.target_out_path, result_file)
                        dest = self.host_result_path + "/"
                        self._device.pullFile(src, dest)

                    except Exception as e:
                        pass

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      'success' if result else 'fail',\
                      os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file),\
                      self.host_result_path,\
                      self.profile_name,\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_web_app_launching_test(self, *args, **kwargs):
        """docstring for run_web_app_launching_test"""
        result = True
        need_reboot = True
        wait_time = 240
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = ""
        pkg_list_file = "web_app_pkg_list.txt"
        post_processing_exe = "get_web_app_launching_time.py"
        __stdout = __stderr = None
        test_timeout = 500

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            src = os.path.join(self.target_installable_path, test_name, 'file')
            dest = self.target_input_path
            self._device.pushFile(src, dest)

            # UEP bypass: pipe script through stdin instead of direct execution
            cmd = self._target_script_cmd(test_name, target_exe_name,
                  "install {} {}".format(
                  os.path.join(self.target_input_path, pkg_list_file),
                  self.target_out_path))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # UEP bypass: pipe script through stdin instead of direct execution
            cmd = self._target_script_cmd(test_name, target_exe_name,
                  "run {} {}".format(
                  os.path.join(self.target_input_path, pkg_list_file),
                  self.target_out_path))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            with open(os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file), 'r') as f:
                for line in f:
                    try:
                        # ignore comment
                        if re.match(r'^#.*', line):
                            continue

                        pkg_name, pkg_file = re.split(r'[ \t]+', line.strip())[0:2]
                        result_file = "dlog_" + pkg_name + ".txt"
                        src = os.path.join(self.target_out_path, result_file)
                        dest = self.host_result_path + "/"
                        self._device.pullFile(src, dest)
                    except Exception as e:
                        pass

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      'success' if result else 'fail',\
                      os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file),\
                      self.host_result_path,\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_octane_test(self, *args, **kwargs):
        """docstring for run_octane_test"""
        result = True
        need_reboot = False
        wait_time = 80
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = "octane_result.png"
        post_processing_exe = "octane_get_result.py"
        __stdout = __stderr = None
        test_timeout = 300

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            self._device.pushFile(src, self.target_exe_path)

            src = os.path.join(self.target_installable_path, test_name, 'bin')
            self._device.pushFile(src, self.target_exe_path)

            src = os.path.join(self.target_installable_path, test_name, 'file')
            self._device.pushFile(src, self.target_input_path)

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            ## Run benckmarks
            cmd = "/bin/bash -c " + "\"" + os.path.join(self.target_exe_path, target_exe_name) + " "\
                + os.path.join(self.target_out_path, result_file) + "\""

            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                result = False

            ## Pull result file from device
            src = os.path.join(self.target_out_path, result_file)
            self._device.pullFile(src, self.host_result_path)

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                    test_name,\
                    'success' if result else fail,\
                    os.path.join(self.host_result_path, result_file),\
                    "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result

    def run_glbench_test(self, *args, **kwargs):
        """docstring for run_glbench_test"""
        result = True
        need_reboot = True
        wait_time = 80
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = ""
        pkg_info_file = "glbench_pkg_info.txt"
        test_info_file = "test_info.txt"
        post_processing_exe = "get_frame_data.py"
        __stdout = __stderr = None
        test_timeout = 600

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            src = os.path.join(self.target_installable_path, test_name, 'file')
            dest = self.target_input_path
            self._device.pushFile(src, dest)

            cmd = "/bin/bash -c " + "\" {} {} {} {} {}\"".format(
                  os.path.join(self.target_exe_path, target_exe_name),
                  "install",
                  os.path.join(self.target_input_path, pkg_info_file),
                  os.path.join(self.target_input_path, test_info_file),
                  self.target_out_path)
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            cmd = "/bin/bash -c " + "\" {} {} {} {} {}\"".format(
                  os.path.join(self.target_exe_path, target_exe_name),
                  "run",
                  os.path.join(self.target_input_path, pkg_info_file),
                  os.path.join(self.target_input_path, test_info_file),
                  self.target_out_path)
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            pkg_name = ""
            with open(os.path.join(self.target_installable_path, test_name, 'file', pkg_info_file), 'r') as f:
                for line in f:
                    # ignore comment
                    if re.match(r'^#.*', line):
                        continue

                    pkg_name = re.split(r'[ \t]+', line.strip())[0]

            with open(os.path.join(self.target_installable_path, test_name, 'file', test_info_file), 'r') as f:
                for line in f:
                    # ignore comment
                    if re.match(r'^#.*', line):
                        continue

                    sub_test_name = re.split(r'[ \t]+', line.strip())[6]
                    result_file = pkg_name + "_" + sub_test_name + ".txt"
                    src = os.path.join(self.target_out_path, result_file)
                    dest = self.host_result_path + "/"
                    self._device.pullFile(src, dest)

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      'success' if result else 'fail',\
                      os.path.join(self.target_installable_path, test_name, 'file', pkg_info_file),\
                      os.path.join(self.target_installable_path, test_name, 'file', test_info_file),\
                      self.host_result_path,\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_process_memory_usage_test(self, *args, **kwargs):
        """docstring for run_process_memory_usage_test"""
        if getattr(self, "memory_rigor", {}).get("enabled", False):
            runner = self._get_memory_runner()
            return runner.export_legacy("process_memory_usage_test")


        result = True
        need_reboot = True
        wait_time = 300
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = "memps.txt"
        post_processing_exe = "get_process_memory_usage.py"
        extra_result_file = "dlog_" + test_name + ".txt"
        __stdout = __stderr = None
        test_timeout = 60

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            if not os.path.exists(os.path.join(self.host_result_path, result_file)):
                logging.debug("run test")

                src = os.path.join(self.script_path, test_name, 'target')
                dest = self.target_exe_path
                self._device.pushFile(src, dest)

                # memps is absent from the TV image (it ships vd_memps
                # instead, which provides no "memps" binary); install from
                # the repo like booting_time installs systemd-analyze.
                if self.install_package_from_repo("memps") == False:
                    raise Exception("Failed to install memps")

                if need_reboot:
                    reseted_time = time.time()
                    if not self._device.reboot_device():
                        raise Exception("fail to reboot device")

                    while wait_time > (time.time() - reseted_time):
                        logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                        time.sleep(10)
                    # TCP target: force disconnect+connect after the post-reboot
                    # wait; an attach made during early boot can be stale ("closed").
                    self._device.refresh_tcp_connection()


                #run test in target
                # UEP-safe: pipe script via stdin instead of executing the file
                cmd = self._target_script_cmd(test_name, target_exe_name, os.path.join(self.target_out_path, result_file))
                remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
                if remained_time == 0:
                    logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                    self._device.reboot_device()
                    raise Exception("timeout")

                src = os.path.join(self.target_out_path, result_file)
                dest = self.host_result_path + "/"
                self._device.pullFile(src, dest)

                src = os.path.join(self.target_out_path, extra_result_file)
                dest = self.host_extra_result_path + "/"
                self._device.pullFile(src, dest)

            else:
                logging.debug("result already exist")
                cmd = "cp {} {}".format(os.path.join(self.host_extra_result_path, "dlog_memory_usage_test.txt"),\
                                        os.path.join(self.host_extra_result_path, extra_result_file))
                os.system(cmd)

            if not os.path.exists(os.path.join(self.host_result_path, result_file)):
                raise Exception("fail to pull test result file")

            if not os.path.exists(os.path.join(self.host_extra_result_path, extra_result_file)):
                raise Exception("fail to pull extra result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_memory_info_test(self, *args, **kwargs):
        """docstring for run_memory_info_test"""
        if getattr(self, "memory_rigor", {}).get("enabled", False):
            runner = self._get_memory_runner()
            return runner.export_legacy("memory_info_test")


        result = True
        need_reboot = True
        wait_time = 300
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_files = ["memps.txt", "meminfo.txt", "vmallocinfo.txt"]
        post_processing_exe = "get_memory_info.py"
        extra_result_file = "dlog_" + test_name + ".txt"
        __stdout = __stderr = None
        test_timeout = 60

        logging.debug(coded_str("Start, {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            need_run_test = False
            for f in result_files:
                if not os.path.exists(os.path.join(self.host_result_path, f)):
                    need_run_test = True

            if need_run_test:
                logging.debug("run test")

                src = os.path.join(self.script_path, test_name, 'target')
                dest = self.target_exe_path
                self._device.pushFile(src, dest)

                # memps is absent from the TV image (it ships vd_memps
                # instead, which provides no "memps" binary); install from
                # the repo like booting_time installs systemd-analyze.
                if self.install_package_from_repo("memps") == False:
                    raise Exception("Failed to install memps")

                if need_reboot:
                    reseted_time = time.time()
                    if not self._device.reboot_device():
                        raise Exception("fail to reboot device")

                    while wait_time > (time.time() - reseted_time):
                        logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                        time.sleep(10)
                    # TCP target: force disconnect+connect after the post-reboot
                    # wait; an attach made during early boot can be stale ("closed").
                    self._device.refresh_tcp_connection()


                #run test in target
                cmd_args = ""
                for f in result_files:
                    cmd_args += os.path.join(self.target_out_path, f) + " "

                # UEP-safe: pipe script via stdin instead of executing the file
                cmd = self._target_script_cmd(test_name, target_exe_name, cmd_args)
                remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
                if remained_time == 0:
                    logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                    self._device.reboot_device()
                    raise Exception("timeout")

                dest = self.host_result_path + "/"
                for f in result_files:
                    src = os.path.join(self.target_out_path, f)
                    self._device.pullFile(src, dest)
                    time.sleep(2)

                extra_result_file = "dlog_" + test_name + ".txt"
                src = os.path.join(self.target_out_path, extra_result_file)
                dest = self.host_extra_result_path + "/"
                self._device.pullFile(src, dest)

            else:
                logging.debug("result already exist")
                cmd = "cp {} {}".format(os.path.join(self.host_extra_result_path, "dlog_memory_usage_test.txt"),\
                                        os.path.join(self.host_extra_result_path, extra_result_file))
                os.system(cmd)

            for f in result_files:
                if not os.path.exists(os.path.join(self.host_result_path, f)):
                    raise Exception("fail to pull test result file")

            if not os.path.exists(os.path.join(self.host_extra_result_path, extra_result_file)):
                raise Exception("fail to pull extra result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      self.profile_name,\
                      os.path.join(self.host_result_path, result_files[1]),\
                      os.path.join(self.host_result_path, result_files[2]),\
                      os.path.join(self.host_result_path, result_files[0]),\
                      "-o", self.report_file]
            print(" ".join(cmd))

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result

    def run_dependency_info_test(self, *args, **kwargs):
        """docstring for run_dependency_info_test"""

        result = True
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        post_processing_exe = "parse_dep_info_result.py"
        report_file = "_dep_info_report.txt"
        __stdout = __stderr = None
        test_timeout = 40 * 60

        logging.debug(coded_str("Start, {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.target_installable_path, test_name, 'file')
            self._device.pushFile(src, self.target_input_path)

            src = os.path.join(self.script_path, test_name, 'target')
            self._device.pushFile(src, self.target_exe_path)

            logging.debug("Start gathering dependency data.")

            target_dir = ["/usr/lib", "/usr/bin"]

            for dir in target_dir:
                #run test on target
                cmd = "/bin/bash -c " + "\"" + os.path.join(self.target_exe_path, target_exe_name) +\
                     " " + dir + " " +self.target_input_path + " " +\
                     os.path.join(self.target_out_path, "dep-info") + "\""

                remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
                if remained_time == 0:
                    logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                    raise Exception("timeout")

            src = os.path.join(self.target_out_path, "dep-info")
            output_path = os.path.join(self.host_result_path, "dep-info")
            self._device.pullFile(src, output_path)
            time.sleep(1)

            for root, subdirs, files in os.walk(output_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    logging.debug("make graph for {}".format(file_path))
                    cmd = os.path.join(self.script_path, test_name, 'host','make_graph') + " " + \
                        file_path + " --simple=" + \
                        os.path.join(self.script_path, test_name, 'host', 'ignore_libs_list.txt')
                    os.system(cmd)

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            self._device.reboot_device()
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                    test_name,\
                    "success" if result else "fail",\
                    os.path.join(self.host_result_path, "dep-info", report_file),\
                    "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result

    def run_dali_3d_ui_test(self, *args, **kwargs):
        """docstring for run_dali_3d_ui_test"""

        result = True
        need_reboot = False
        wait_time = 100
        test_name = kwargs.get('name')
        target_exe_name = test_name + ".sh"
        result_file = ""
        package_name = "com.samsung.dali-demo"
        pkg_list_file = "pkg_info_list"
        post_processing_exe = "parse_enlightment_info.py"
        index_file = "index.html"
        __stdout = __stderr = None
        test_timeout = 90

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            src = os.path.join(self.target_installable_path, test_name, 'file')
            dest = self.target_input_path
            self._device.pushFile(src, dest)

            # For version 10.0 and later, try repo download first, fallback to localpath
            version_str = self._testinfo['test_profile_data'].get('version', '0')
            try:
                version_num = float(version_str)
            except (ValueError, TypeError):
                version_num = 0.0

            if version_num >= 10.0:
                if self.install_package_from_repo(package_name) == False:
                    logging.debug(coded_str("Failed to install from repo, falling back to localpath",
                                            fore='yellow', bold=True))
                    if self.install_package_from_localpath(test_name) == False:
                        raise Exception("Failed to install {}".format(package_name))
            else:
                if self.install_package_from_localpath(test_name) == False:
                    raise Exception("Failed to install {}".format(package_name))

            # UEP bypass: pipe script through stdin instead of direct execution
            cmd = self._target_script_cmd(test_name, target_exe_name,
                  "install {} {}".format(
                  os.path.join(self.target_input_path, pkg_list_file),
                  self.target_out_path))

            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # UEP bypass: pipe script through stdin instead of direct execution
            cmd = self._target_script_cmd(test_name, target_exe_name,
                  "run {} {}".format(
                  os.path.join(self.target_input_path, pkg_list_file),
                  self.target_out_path))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            with open(os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file), 'r') as f:
                for line in f:
                    try:
                        # ignore comment
                        if re.match(r'^#.*', line):
                            continue

                        pkg_name = re.split(r'[ \t]+', line.strip())[0]
                        result_file = "enlightenment_info_" + pkg_name + ".txt"
                        src = os.path.join(self.target_out_path, result_file)
                        dest = self.host_result_path + "/"
                        self._device.pullFile(src, dest)

                        #TODO: extrea result

                        extra_result_file = "dlog_" + test_name + "_" + pkg_name + ".txt"
                        src = os.path.join(self.target_out_path, extra_result_file)
                        dest = self.host_extra_result_path + "/"
                        self._device.pullFile(src, dest)

                    except Exception as e:
                        pass

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.target_installable_path, test_name, 'file', pkg_list_file),\
                      self.host_result_path,\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()

            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_ffmpeg_benchmark_test(self, *args, **kwargs):
        """docstring for run_ffmpeg_benchmark_test

        Installs ffmpeg packages on the device, preferring local RPMs from
        target_installable/<profile>/ffmpeg_benchmark_test/file/ and falling
        back to repo download for packages not available locally.
        Pushes test video files from test_source/video, runs the ffbench.sh
        benchmark script on the device, pulls the result file, and runs the
        host-side post-processing script.
        """
        result = True
        need_reboot = True
        wait_time = 80
        test_name = kwargs.get('name')
        target_exe_name = "ffbench.sh"
        result_file = "ffmpeg_benchmark_result.txt"
        post_processing_exe = "get_ffbench_result.py"
        __stdout = __stderr = None
        test_timeout = 3600

        # Packages to install on the device (local RPMs preferred, repo as fallback)
        ffmpeg_packages = [
            "ffmpeg-tool",
            "libavformat",
            "libswresample",
            "libswscale",
            "libavfilter",
            "libavcodec",
            "libavutil",
        ]

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            # Step 1: Push ffbench.sh to device
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            # Step 2: Install ffmpeg packages (local RPM first, repo fallback)
            self.install_packages_local_first(ffmpeg_packages, test_name)

            # Verify ffmpeg is installed
            verify_cmd = "ffmpeg -version 2>&1 | head -3"
            remained_time = self._device.executeCmd_timeout(verify_cmd, 30)
            if remained_time == 0:
                raise Exception("ffmpeg is not installed correctly on device")

            # Step 3: Push test video files to device
            # test_source/video is at the project root level (parent of standalone/)
            # Only push h264/ and hevc/ subdirectories (skip .y4m and other files
            # that ffbench.sh does not use)
            cur_path = os.path.dirname(os.path.abspath(__file__))
            video_source_path = os.path.join(os.path.dirname(cur_path), 'test_source', 'video')
            target_video_path = self.target_input_path

            if not os.path.exists(video_source_path):
                raise Exception("test video source path does not exist: {}".format(video_source_path))

            # Push video files individually (sdb push of directories can be unreliable)
            video_subdirs = ['h264', 'hevc']
            for subdir in video_subdirs:
                subdir_src = os.path.join(video_source_path, subdir)
                if not os.path.isdir(subdir_src):
                    logging.debug("Warning: video subdirectory not found: {}".format(subdir))
                    continue

                # Create the subdirectory on device first
                target_subdir = os.path.join(self.target_input_path, subdir)
                mkdir_cmd = "mkdir -p {}".format(target_subdir)
                self._device.executeCmd_timeout(mkdir_cmd, 30)

                # Push each video file individually
                for video_file in os.listdir(subdir_src):
                    file_src = os.path.join(subdir_src, video_file)
                    if os.path.isfile(file_src):
                        logging.debug("Pushing {} to device".format(file_src))
                        self._device.pushFile(file_src, target_subdir)

            # Step 4: Reboot device and wait for stability before running benchmark
            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # Step 5: Run ffbench.sh on device (pipe mode: UEP bypass on TV)
            cmd = self._target_script_cmd(
                test_name, target_exe_name,
                target_video_path + " " + os.path.join(self.target_out_path, result_file))

            logging.debug("Running ffbench on device: {}".format(cmd))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            # Step 6: Pull result file from device
            src = os.path.join(self.target_out_path, result_file)
            dest = self.host_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, result_file)):
                raise Exception("fail to pull test result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_gstreamer_benchmark_test(self, *args, **kwargs):
        """docstring for run_gstreamer_benchmark_test

        Installs GStreamer packages on the device, preferring local RPMs from
        target_installable/<profile>/gstreamer_benchmark_test/file/ and falling
        back to repo download for packages not available locally.
        Pushes test video files from test_source/video, runs the gstbench.sh
        benchmark script on the device, pulls the result file, and runs the
        host-side post-processing script.
        """
        result = True
        need_reboot = True
        wait_time = 80
        test_name = kwargs.get('name')
        target_exe_name = "gstbench.sh"
        result_file = "gstreamer_benchmark_result.txt"
        post_processing_exe = "get_gstbench_result.py"
        __stdout = __stderr = None
        test_timeout = 3600

        # GStreamer packages to install on the device (local RPMs preferred, repo as fallback)
        gstreamer_packages = [
            "gstreamer",
            "gst-plugins-base",
            "gst-plugins-good",
            "gst-plugins-bad",
            "gst-plugins-ugly",
            "gst-libav",
        ]

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            # Step 1: Push gstbench.sh and test scripts to device
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            # Step 2: Install GStreamer packages (local RPM first, repo fallback)
            self.install_packages_local_first(gstreamer_packages, test_name)

            # Verify gstreamer is installed
            verify_cmd = "gst-launch-1.0 --version 2>&1 | head -3"
            remained_time = self._device.executeCmd_timeout(verify_cmd, 30)
            if remained_time == 0:
                raise Exception("gstreamer is not installed correctly on device")

            # Step 3: Push test video files to device
            # test_source/video is at the project root level (parent of standalone/)
            # Only push h264/ and hevc/ subdirectories (skip .y4m and other files
            # that gstbench.sh does not use)
            cur_path = os.path.dirname(os.path.abspath(__file__))
            video_source_path = os.path.join(os.path.dirname(cur_path), 'test_source', 'video')
            target_video_path = self.target_input_path

            if not os.path.exists(video_source_path):
                raise Exception("test video source path does not exist: {}".format(video_source_path))

            # Push video files individually (sdb push of directories can be unreliable)
            video_subdirs = ['h264', 'hevc']
            for subdir in video_subdirs:
                subdir_src = os.path.join(video_source_path, subdir)
                if not os.path.isdir(subdir_src):
                    logging.debug("Warning: video subdirectory not found: {}".format(subdir))
                    continue

                # Create the subdirectory on device first
                target_subdir = os.path.join(self.target_input_path, subdir)
                mkdir_cmd = "mkdir -p {}".format(target_subdir)
                self._device.executeCmd_timeout(mkdir_cmd, 30)

                # Push each video file individually
                for video_file in os.listdir(subdir_src):
                    file_src = os.path.join(subdir_src, video_file)
                    if os.path.isfile(file_src):
                        logging.debug("Pushing {} to device".format(file_src))
                        self._device.pushFile(file_src, target_subdir)

            # Step 4: Reboot device and wait for stability before running benchmark
            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # Step 5: Run gstbench.sh on device (pipe mode: UEP bypass on TV)
            cmd = self._target_script_cmd(
                test_name, target_exe_name,
                target_video_path + " " + os.path.join(self.target_out_path, result_file))

            logging.debug("Running gstbench on device: {}".format(cmd))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            # Step 6: Pull result file from device
            src = os.path.join(self.target_out_path, result_file)
            dest = self.host_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, result_file)):
                raise Exception("fail to pull test result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_tflite_benchmark_test(self, *args, **kwargs):
        """docstring for run_tflite_benchmark_test

        Installs TensorFlow2 Lite packages on the device, preferring local RPMs
        from target_installable/<profile>/tflite_benchmark_test/file/ and
        falling back to repo download for packages not available locally.
        Pushes .tflite model files from test_source/model, runs the tflitebench.sh
        benchmark script on the device, pulls the result file, and runs the
        host-side post-processing script.
        """
        result = True
        need_reboot = True
        wait_time = 80
        test_name = kwargs.get('name')
        target_exe_name = "tflitebench.sh"
        result_file = "tflite_benchmark_result.txt"
        post_processing_exe = "get_tflitebench_result.py"
        __stdout = __stderr = None
        test_timeout = 3600

        # TFLite packages to install on the device (local RPMs preferred, repo as fallback)
        tflite_packages = [
            "tensorflow2-lite-util",
            "tensorflow2-lite-flatbuf-schema",
        ]

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            # Step 1: Push tflitebench.sh to device
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            # Step 2: Install TFLite packages (local RPM first, repo fallback)
            self.install_packages_local_first(tflite_packages, test_name)

            # Verify tflite_benchmark_model is installed
            verify_cmd = "which tflite_benchmark_model 2>/dev/null || find / -name tflite_benchmark_model -type f 2>/dev/null | head -1"
            remained_time = self._device.executeCmd_timeout(verify_cmd, 30)
            if remained_time == 0:
                raise Exception("tflite_benchmark_model is not installed correctly on device")

            # Step 3: Push .tflite model files to device
            # test_source/model is at the project root level (parent of standalone/)
            cur_path = os.path.dirname(os.path.abspath(__file__))
            model_source_path = os.path.join(os.path.dirname(cur_path), 'test_source', 'model')
            target_model_path = self.target_input_path

            if not os.path.exists(model_source_path):
                raise Exception("test model source path does not exist: {}".format(model_source_path))

            # Push each .tflite model file individually
            for model_file in os.listdir(model_source_path):
                file_src = os.path.join(model_source_path, model_file)
                if os.path.isfile(file_src) and model_file.endswith('.tflite'):
                    logging.debug("Pushing {} to device".format(file_src))
                    self._device.pushFile(file_src, target_model_path)

            # Step 4: Reboot device and wait for stability before running benchmark
            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # Step 5: Run tflitebench.sh on device
            cmd = "/bin/bash -c " + "\"" + os.path.join(self.target_exe_path, target_exe_name) + " " + \
                  target_model_path + " " + \
                  os.path.join(self.target_out_path, result_file) + "\""

            logging.debug("Running tflitebench on device: {}".format(cmd))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            # Step 6: Pull result file from device
            src = os.path.join(self.target_out_path, result_file)
            dest = self.host_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, result_file)):
                raise Exception("fail to pull test result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_kernel_benchmark_test(self, *args, **kwargs):
        """docstring for run_kernel_benchmark_test

        Pushes kernel benchmark RPM packages and pre-compiled binaries from
        test_source/kernel to the device, runs the kernelbench.sh benchmark
        script on the device (which installs RPMs, runs tinymembench, schbench,
        ipc-benchmark, hackbench, whetstone, dhrystone, coremark_multi,
        coremark_single), pulls the result file, and runs the host-side
        post-processing script.
        """
        result = True
        need_reboot = False
        wait_time = 80
        test_name = kwargs.get('name')
        target_exe_name = "kernelbench.sh"
        result_file = "kernel_benchmark_result.txt"
        post_processing_exe = "get_kernelbench_result.py"
        __stdout = __stderr = None
        test_timeout = 7200  # 2 hours for all kernel benchmarks

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            # Step 1: Push kernelbench.sh and runner scripts to device
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            # Step 2: Push kernel benchmark RPM packages and binaries to device
            # test_source/kernel is at the project root level (parent of standalone/)
            cur_path = os.path.dirname(os.path.abspath(__file__))
            kernel_source_path = os.path.join(os.path.dirname(cur_path), 'test_source', 'kernel')
            target_kernel_path = self.target_input_path

            if not os.path.exists(kernel_source_path):
                raise Exception("test kernel source path does not exist: {}".format(kernel_source_path))

            # Push all files from test_source/kernel to device
            for kernel_file in os.listdir(kernel_source_path):
                file_src = os.path.join(kernel_source_path, kernel_file)
                if os.path.isfile(file_src):
                    logging.debug("Pushing {} to device".format(file_src))
                    self._device.pushFile(file_src, target_kernel_path)

            # Step 3: Reboot device and wait for stability before running benchmark
            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # Step 4: Run kernelbench.sh on device (pipe mode: UEP bypass on TV)
            cmd = self._target_script_cmd(
                test_name, target_exe_name,
                target_kernel_path + " " + os.path.join(self.target_out_path, result_file))

            logging.debug("Running kernelbench on device: {}".format(cmd))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            # Step 5: Pull result file from device
            src = os.path.join(self.target_out_path, result_file)
            dest = self.host_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, result_file)):
                raise Exception("fail to pull test result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def run_dotnet_benchmark_test(self, *args, **kwargs):
        """docstring for run_dotnet_benchmark_test

        Installs .NET runtime packages (coreclr, corefx-native, mscorlib,
        corefx-managed), preferring local RPMs from
        target_installable/<profile>/dotnet_benchmark_test/file/ and falling
        back to repo download for packages not available locally.
        Pushes and installs the local microbench RPM from test_source/dotNet,
        locates MicroBenchmarks.dll, runs the dotnetbench.sh benchmark script
        on the device, pulls the result file, and runs the host-side
        post-processing script.
        """
        result = True
        need_reboot = False
        wait_time = 80
        test_name = kwargs.get('name')
        target_exe_name = "dotnetbench.sh"
        result_file = "dotnet_benchmark_result.txt"
        post_processing_exe = "get_dotnetbench_result.py"
        __stdout = __stderr = None
        test_timeout = 7200  # 2 hours for all .NET benchmark cases

        # .NET runtime packages to install (local RPMs preferred, repo as fallback)
        dotnet_repo_packages = [
            "coreclr",
            "corefx-native",
            "mscorlib",
            "corefx-managed",
        ]

        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            # Step 1: Push dotnetbench.sh to device
            src = os.path.join(self.script_path, test_name, 'target')
            dest = self.target_exe_path
            self._device.pushFile(src, dest)

            # Step 2: Install .NET runtime packages (local RPM first, repo fallback)
            self.install_packages_local_first(dotnet_repo_packages, test_name)

            # Step 3: Push and install the local microbench RPM from test_source/dotNet
            cur_path = os.path.dirname(os.path.abspath(__file__))
            dotnet_source_path = os.path.join(os.path.dirname(cur_path), 'test_source', 'dotNet')

            if not os.path.exists(dotnet_source_path):
                raise Exception("test dotnet source path does not exist: {}".format(dotnet_source_path))

            # Push each local microbench RPM and install it right away by its
            # exact filename. A "for r in .../*.rpm" glob loop does not survive
            # the sdb shell + bash -c quoting layers, so install explicitly.
            for f in os.listdir(dotnet_source_path):
                file_src = os.path.join(dotnet_source_path, f)
                if os.path.isfile(file_src) and f.endswith('.rpm'):
                    logging.debug("Pushing {} to device".format(file_src))
                    self._device.pushFile(file_src, self.target_input_path)

                    install_cmd = "/bin/bash -c \"" + \
                        "rpm -ivh --force --nodeps {} ; sync\"".format(
                            os.path.join(self.target_input_path, f))
                    remained_time = self._device.executeCmd_timeout(install_cmd, 600)
                    if remained_time == 0:
                        raise Exception("timeout installing microbench RPM {} on device".format(f))

            # Step 4: Locate MicroBenchmarks.dll on the device
            # The microbench package typically installs into a known directory.
            # Search common locations and fall back to a filesystem find.
            # executeCmd_timeout does not return stdout, so write the detected
            # dir to a marker file on the device and pull it back.
            bench_dir = None
            candidates = [
                "/opt/usr/home/owner/media/Bench/MicroBench",
                "/opt/usr/globalapps/Bench/MicroBench",
                "/opt/usr/benchmark/MicroBench",
                "/opt/benchmark/MicroBench",
            ]
            marker = "/tmp/tpms_dotnet_bench_dir"
            self._device.executeCmd_timeout("rm -f " + marker, 10)

            for cand in candidates:
                check_cmd = "test -f {}/MicroBenchmarks.dll && echo {} > {}".format(cand, cand, marker)
                self._device.executeCmd_timeout(check_cmd, 30)

            # Fall back to a filesystem find if none of the candidates matched
            find_cmd = "/bin/bash -c \"if [ ! -f {m} ]; then " \
                       "d=\\$(find /opt /usr /home -name MicroBenchmarks.dll 2>/dev/null | head -1); " \
                       "[ -n \\\"\\$d\\\" ] && dirname \\\"\\$d\\\" > {m}; fi\"".format(m=marker)
            self._device.executeCmd_timeout(find_cmd, 120)

            self._device.pullFile(marker, "./")
            marker_local = os.path.basename(marker)
            if os.path.exists(marker_local):
                with open(marker_local, 'r') as f:
                    found = f.read().strip().split('\n')[0].strip()
                    if found and found != "." and found != "/":
                        bench_dir = found
                os.remove(marker_local)
            self._device.executeCmd_timeout("rm -f " + marker, 10)

            if not bench_dir:
                raise Exception("MicroBenchmarks.dll not found on device")

            logging.debug("MicroBenchmarks.dll located at: {}".format(bench_dir))

            # Step 5: Reboot device and wait for stability before running benchmark
            if need_reboot:
                reseted_time = time.time()
                if not self._device.reboot_device():
                    raise Exception("fail to reboot device")

                while wait_time > (time.time() - reseted_time):
                    logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                    time.sleep(10)
                # TCP target: force disconnect+connect after the post-reboot
                # wait; an attach made during early boot can be stale ("closed").
                self._device.refresh_tcp_connection()


            # Step 6: Run dotnetbench.sh on device (pipe mode: UEP bypass on TV)
            cmd = self._target_script_cmd(
                test_name, target_exe_name,
                bench_dir + " " + os.path.join(self.target_out_path, result_file))

            logging.debug("Running dotnetbench on device: {}".format(cmd))
            remained_time = self._device.executeCmd_timeout(cmd, test_timeout)
            if remained_time == 0:
                logging.debug("{}: test timeout in target ({})".format(test_name, cmd))
                self._device.reboot_device()
                raise Exception("timeout")

            # Step 7: Pull result file from device
            src = os.path.join(self.target_out_path, result_file)
            dest = self.host_result_path + "/"
            self._device.pullFile(src, dest)

            if not os.path.exists(os.path.join(dest, result_file)):
                raise Exception("fail to pull test result file")

        except Exception as err:
            traceback.print_exc()
            logging.debug(err)
            result = False

        finally:
            cmd = [os.path.join(self.script_path, test_name, 'host', post_processing_exe),\
                      test_name,\
                      "success" if result else "fail",\
                      os.path.join(self.host_result_path, result_file),\
                      "-o", self.report_file]
            print(f"cmd: {' '.join(cmd)}")

            sp = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            __stdout, __stderr = sp.communicate()
            __stdout = __stdout.decode()
            __stderr = __stderr.decode()
            logging.debug("{}: post_processing: {}, returncode={}, stdout=\"{}\", stderr=\"{}\""\
                   .format(inspect.stack()[0][3], test_name, sp.returncode, __stdout, __stderr))

        return result


    def runTest(self):
        """docstring for runTest"""
        ret = True
        rigor_failed = False
        logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

        try:
            if not self.setup_test_env():
                raise Exception("fail to setup test environment")

            self._device.root_on()
            self._device.remount_rootfs_rw()
            self.clear_target_data()

            self.append_report_ver()
            self.append_target_info()

            self._device.reboot_device()

            for t in self.performance_test_list:
                if t['enable']:
                    ret = t['func'](**t)
                    if self.memory_rigor['enabled'] and t['name'] in ('wait_for_stability', 'memory_usage_test', 'process_memory_usage_test', 'memory_info_test') and ret is False:
                        rigor_failed = True

#            self.gen_groovy_str()
            ret_val = self.gen_perfpublisher_xml()
            if ret_val != 0:
                raise Exception("fail to generate perfpublisher xml")

#            self.chown_result_file()

        except Exception as e:
            logging.error(e)
            ret = False

        return False if rigor_failed else ret

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--test_profile', required=True, metavar='profile', help="test profile")
    parser.add_argument('-c', '--test_config', required=True, metavar='config file', help="configuration file")
    parser.add_argument('-o', '--output_path', required=True, metavar='path', help="path for output(result) file")
    args = parser.parse_args()
    return args

def get_dev_serial(pattern):
    dev_serial = []
    temp_device = device(dev_serial='dummy')
    dev_list = temp_device.get_device_list()

    for d in dev_list.split('\n'):
        dev_info = re.split(r'[ \t]+', d)

        if len(dev_info) != 3:
           continue


        for p in pattern.strip('[] \t').split(','):
            p = p.strip()
            m = re.match(p, dev_info[2])
            if m:
                dev_serial.append(dev_info[0])
                break

    return dev_serial

def setup_standalone_env(config_file, test_profile):
    initLogging()
    logging.debug(coded_str("\tdo {}".format(inspect.stack()[0][3]), fore='red', bold=True))

    __test_config = None
    __test_device = None
    try:

        config_parser = configparser.ConfigParser(interpolation=None)

        config_parser.read(config_file)

        for s in config_parser.sections():
            if s == test_profile:
                __test_config = dict(config_parser.items(s))
                __test_config['name'] = s
                break

        if not __test_config:
            raise Exception("no test config")

        dev_serial = get_dev_serial(__test_config['dev_name_pattern'])
        # The old "!= 1" check reported "more than one" even when ZERO
        # devices matched (typical when the sdb-over-TCP link dropped);
        # split the cases so the actual failure is visible.
        if len(dev_serial) == 0:
            raise Exception("no device connected (dev_name_pattern: %s); check sdb connection" % __test_config['dev_name_pattern'])
        if len(dev_serial) > 1:
            raise Exception("devices are connected more than one")

        __test_device = device(dev_serial=dev_serial[0])
        if not __test_device:
            raise Exception("fail to create device")

    except Exception as e:
        logging.error(e)
        traceback.print_exc()

    return __test_config, __test_device

def run(test_profile, config_file, output_path, reboot_func=None):
    ''' docstring'''
    test_config, test_device = setup_standalone_env(config_file, test_profile)
    print(test_config, test_device)
    if reboot_func:
        test_device.reboot_device = reboot_func
    test_perf = TestPerformance(test_profile=test_profile, config=test_config, device=test_device, output_path=output_path)
    test_perf.runTest()


if __name__ == '__main__':
    try:
        args = parse_args()
        test_config, test_device = setup_standalone_env(args.test_config, args.test_profile)
        print(test_config, test_device)
        test_perf = TestPerformance(test_profile=args.test_profile, config=test_config, device=test_device, output_path=args.output_path)
        ret = test_perf.runTest()
        if not ret:
            print("ERROR: runTest() returned False - performance test failed")
            sys.exit(1)
    except Exception as e:
        logging.error(e)
        traceback.print_exc()
        sys.exit(1)

