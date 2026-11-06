#!/usr/bin/env python3
import sys
import os
import logging
import time
import subprocess
import inspect
import threading
import re
import datetime
import traceback
import signal


MAX_TRACING_TIME = 30
TEST_TIMEOUT = 60

def get_start_of_capture(filename):
    """Get lastest timestamp from dlogutil output"""

    dlog_line = open(filename).readline()
    timestamp_re = re.compile("\\d+:\\d+:\\d+\\.\\d+")
    last_timestamp = timestamp_re.search(dlog_line).group()[:-6]
    return last_timestamp


def getAppLaunchTime(app_id , start_time_str, target_execute_function):
    dlog = target_execute_function("dlogutil -v threadtime -d")
    launchStartOldRe = re.compile("launch request : appid\(%s\)" % app_id)
    launchStartRe = re.compile("request cmd\(0\) : appid\(%s\)" % app_id)
    realApplicationName = re.sub(".*\..*\.", "", app_id)
    launchDoneRe = re.compile("%s:Application:(Launching|resume):done" % realApplicationName)
    launchStart = None
    launchDone = None

    for line in dlog.split('\n'):
        if launchStartRe.search(line) != None or launchStartOldRe.search(line) != None:
            launchStart = line
        if launchDoneRe.search(line) != None:
            launchDone = line

    if launchStart == None:
        logging.debug("Failed to find launch request for %s!" % app_id)
#        return None

    if launchDone == None:
        logging.debug("Failed to find launching done event for %s!" % app_id)
        return None

    timestampRe = re.compile("\d+:\d+:\d+\.\d+")

    launchDoneTimestampString = timestampRe.search(launchDone).group()
    launchDoneTimestamp = datetime.datetime.strptime(launchDoneTimestampString, "%H:%M:%S.%f")

    start_capture_timestamp = datetime.datetime.strptime(start_time_str, "%H:%M:%S.%f")

    if launchStart != None:
        launchStartTimestampString = timestampRe.search(launchStart).group()
        launchStartTimestamp = datetime.datetime.strptime(launchStartTimestampString, "%H:%M:%S.%f")
        delta = launchDoneTimestamp - launchStartTimestamp
        deltaMs = (delta.seconds * 10 ** 6 + delta.microseconds) / 10.**3
        logging.debug("Application start launching at %s finished at %s delta is %.2f milliseconds",
                  launchStartTimestampString, launchDoneTimestampString, deltaMs)
    else:
        delta = launchDoneTimestamp - start_capture_timestamp
        deltaMs = (delta.seconds * 10 ** 6 + delta.microseconds) / 10.**3
        launchStartTimestampString = None
        logging.debug("Application start launching at %s finished at %s delta is %.2f milliseconds",
                  start_time_str, launchDoneTimestampString, deltaMs)

    logging.debug("Launch done timestamp is %s" % (str(launchDoneTimestamp)))
    return deltaMs


def timeMeasurmentSwap(number_or_runs = 1):
    SLEEP_INTERVAL = 5
    scriptPath = os.path.join(os.getcwd(), os.path.dirname(sys.argv[0]), '..')
    post_processing_exe = "post_process_results.py"
    jobDir = os.getcwd()
    wait_time = 30
    device = "device"
    os.environ['__TRACE_PARCER'] = os.path.join(scriptPath, 'swap', 'trace_parser')
    os.environ['PATH'] = os.environ['PATH'] + ":%s" % (os.environ['__TRACE_PARCER'])


    result = True
    TEST_TIMEOUT = 60
    times = {}

    instrumentationsFile = os.path.join(scriptPath, 'swap', 'conf', 'user_space_inst_list.py')
    confFile = os.path.join(scriptPath, 'swap', 'conf', 'conf.py')
    scriptsPath = os.path.join(scriptPath, 'scripts')
    swapPath = os.path.join(scriptPath, 'swap')
    enableHighlightPath = os.path.join(scriptPath, '..', 'target', 'enable_highlight.sh')
    disableHighlightPath = os.path.join(scriptPath, '..', 'target', 'disable_highlight.sh')

    os.system("sdb root on")
    os.system("sdb push %s /root/enable_highlight.sh" % enableHighlightPath)
    os.system("sdb push %s /root/disable_highlight.sh" % disableHighlightPath)


    logging.debug("Enabling Highlight")
    os.system("sdb shell sh /root/enable_highlight.sh")

    logging.debug("Enabled")

    sys.path.append(scriptsPath)
    import generateNmCache
    sys.path.append(swapPath)
    import func_profiling
    import parse_trace
    import itertools

    try:
        tryCount = 0
        totalTime = 0
        result = True
        applicationName = sys.argv[1]
        applicationPath = sys.argv[2]


        logging.debug("[%s] Preparation phase started" % applicationName)
        startingTimestamp = time.time()
        instrumentationsFileString = generateNmCache.generateInstrumentationsConfig(applicationName, applicationPath, memoryProfiling = 0)
        if instrumentationsFileString == None:
            return False


        logging.debug("aul_status_update address is %x" % generateNmCache.aul_status_updateAddress)
        os.chdir(scriptsPath)
        applicationDirName = os.path.join(jobDir, "Time_" + applicationName)
        if not os.path.exists(applicationDirName):
            os.mkdir(applicationDirName)


        os.chdir(swapPath)
        fp = open(instrumentationsFile, "w")
        fp.write(instrumentationsFileString)
        fp.close()

        logging.debug("Application %s" % applicationName)
        fp = open(confFile, "w")
        fp.write("""
features = (0x0000000000000000
+ 0x000000000004  #  FL_FUNCTION_PROFILING           = //On/Off the UserSpaceInst
+ 0x000000010000  #  FL_CONTEXT_SWITCH               = //Context switch tracing
)

profile_settings = {
 "system_trace_period": 100,
 "data_message_period": 50,
 "enable_probe_type_support": 1,
}
""")
        fp.close()

        swap_parser = parse_trace.SwapParser()
        libs = {}
        call_counts = {}
        i = 0
        times["[%s]" % applicationName] = time.time() - startingTimestamp
        times["[%s_SuccessSummary]" % applicationName] = 0
        times["[%s_FailSummary]" % applicationName] = 0

        logging.debug("Preparation phase ended, starting repeatable phase")
        while i < number_or_runs:

            logging.debug("[%s_Run%03d(%d_failed)]" % (applicationName, i, tryCount - i))
            startingTimestamp = time.time()
            tryCount += 1
            if tryCount - 1 >= number_or_runs * 2:

                logging.critical("[%s_Run%03d] Application %s failed to start too many times!" % (applicationName,tryCount - 1,applicationName))
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                raise Exception("[%s_Run%03d] Application %s failed to start too many times!" % (applicationName,tryCount - 1,applicationName))

            reseted_time = time.time()
            if not reboot_device_without_uart():
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                raise Exception("fail to reboot device")


            logging.debug("Rebooting device")
            while wait_time > (time.time() - reseted_time):

                logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                time.sleep(10)

            os.system("sdb shell dlogutil -c")
            captureCuttingTimeMilliseconds = func_profiling.main(device, applicationName, applicationPath)
            if captureCuttingTimeMilliseconds == None:

                logging.critical("[%s_Run%03d] Application %s failed to start!" % (applicationName,tryCount - 1,applicationName))
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                continue

            os.system("sdb shell dlogutil -v threadtime -d > /tmp/log")
            captureCuttingTimeMilliseconds += int(captureCuttingTimeMilliseconds * 0.1) # we add 5% more just for sure

            logging.debug("Cutting capture at %d milliseconds" % captureCuttingTimeMilliseconds)
            if captureCuttingTimeMilliseconds > MAX_TRACING_TIME * 10 ** 3:

                logging.debug("Too big cutting time")
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                continue

            i += 1
            trace_file = os.path.join(device, "swap_trace.py")

            logging.debug("Parsing trace...")
            new_libs, new_call_counts = swap_parser.parse_to_lib_dict(trace_file, captureCuttingTimeMilliseconds)

            logging.debug("len(new_libs) = %d" % len(new_libs))

            logging.debug("new_libs = ")

            logging.debug(new_libs)
            fp = open(os.path.join(applicationDirName, "PerLibConsumption_Run%d.csv" % (i-1)), "w")
            currentTotal = 0
            for x in new_libs:
                fp.write("%s %.2f %d\n" % (x, new_libs[x] / 10.**6, new_call_counts[x]))
                currentTotal += new_libs[x]
                if x in libs.keys():
                    libs[x] += new_libs[x]
                    call_counts[x] += new_call_counts[x]
                else:
                    libs[x] = new_libs[x]
                    call_counts[x] = new_call_counts[x]
            fp.close()

            logging.debug("currentTotal = %d" % (currentTotal / 10.**6))
            times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
            times["[%s_SuccessSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]

            logging.debug("[%s_Run%03d] Ended" % (applicationName, i - 1))

        reseted_time = time.time()
        if not reboot_device_without_uart():
            raise Exception("fail to reboot device")

        os.chdir(jobDir)
        fp = open(os.path.join(applicationDirName, "PerLibConsumption.csv"), "w")
        for lib in libs:
            fp.write("%s %.2f %d\n" % (lib, libs[lib] / number_or_runs / (10.**6), call_counts[lib] / number_or_runs))
            totalTime += libs[lib] / number_or_runs
        fp.write("Total %.2f\n" % (totalTime / (10.**6)))
        fp.close()

        while wait_time > (time.time() - reseted_time):

            logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
            time.sleep(10)

        try:
            os.remove(os.path.join("/tmp", applicationName))
        except:
            pass

    except Exception as e:

        logging.critical(e)
        result = False
        raise

    finally:
        #sp_cmd = [os.path.join(scriptPath, post_processing_exe),\
        #       "per_lib_time_profiling",\
        #       "yes" if result else "no",\
        #       "report.xml",\
        #       str(applicationName), \
        #       str(totalTime)]


        #sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #__stdout, __stderr = sp.communicate()

        os.system("rm /tmp/%s" % applicationName)

        logging.debug("Profiling data")
        for x in sorted(times.keys()):

            logging.debug("%s: %d" % (x, times[x]))
        os.chdir(jobDir)


    logging.debug("Disabling Highlight")
    os.system("sdb shell sh /root/disable_highlight.sh")

    logging.debug("Disabled")
    os.chdir(jobDir)
    os.system("rm /tmp/lib*")
    os.system("rm /tmp/ld-*")
    return True

def timeMeasurmentOprofile(number_or_runs = 1):
    def profile(app_id, binary_path):
        SLEEP_INTERVAL = 5
        os.system("sdb root on")

        ld_path = os.path.join(os.path.dirname(binary_path)[:-3], "lib")

        fp = open("prepareBinary.sh", "w")
        cmd = "chsmack -e \"User::Pkg::%s\" %s && \
                echo 0 > /proc/sys/kernel/kptr_restrict && \
                chmod a+r /proc/kallsyms && \
                echo System > /proc/self/attr/current && \
                su owner -c /home/owner/startApplication.sh" % (app_id, binary_path)
        fp.write(cmd)
        fp.close()

        fp = open("startApplication.sh", "w")
        cmd = "source /etc/profile.d/enlightenment.sh && \
                source /etc/profile.d/efl.sh && \
                export LD_LIBRARY_PATH=%s && export AUL_APPID=%s && \
                cd /home/owner && operf %s" % (ld_path, app_id, binary_path)
        fp.write(cmd)
        fp.close()

        os.system("sdb push prepareBinary.sh /home/owner")
        os.system("sdb push startApplication.sh /home/owner")
        os.system("sdb shell /home/owner/prepareBinary.sh &")

        timePassed = 0
        start_time_str = func_profiling.get_start_of_capture()
        while timePassed < MAX_TRACING_TIME:
            time.sleep(SLEEP_INTERVAL)
            timePassed += SLEEP_INTERVAL

            logging.debug("Getting Applaunch time")
            applicationLaunchDeltaMs = func_profiling.getAppLaunchTime(app_id , start_time_str)
            if applicationLaunchDeltaMs != None:
                os.system("sdb shell \"kill -9 \`pidof %s\`\"" % (binary_path))
                return applicationLaunchDeltaMs

        os.system("sdb root off")

    def parse(cuttingTime):
        os.system("sdb shell \"cd /home/owner && opreport -n\" > /tmp/report")
        lines = subprocess.check_output(['cat', '/tmp/report']).split('\n')
        libs = {}
        for line in lines:
            splitted = line.split()
            if len(splitted) == 3 and float(splitted[1]) != 100.00:
                libs[splitted[2]] = float(splitted[1])

        return libs

    scriptPath = os.path.join(os.getcwd(), os.path.dirname(sys.argv[0]), '..')
    post_processing_exe = "post_process_results.py"
    jobDir = os.getcwd()
    wait_time = 30
    os.environ['__TRACE_PARCER'] = os.path.join(scriptPath, 'swap', 'trace_parser')
    os.environ['PATH'] = os.environ['PATH'] + ":%s" % (os.environ['__TRACE_PARCER'])


    result = True
    times = {}

    instrumentationsFile = os.path.join(scriptPath, 'swap', 'conf', 'user_space_inst_list.py')
    confFile = os.path.join(scriptPath, 'swap', 'conf', 'conf.py')
    scriptsPath = os.path.join(scriptPath, 'scripts')
    swapPath = os.path.join(scriptPath, 'swap')
    enableHighlightPath = os.path.join(scriptPath, '..', 'target', 'enable_highlight.sh')
    disableHighlightPath = os.path.join(scriptPath, '..', 'target', 'disable_highlight.sh')
    perfPath = os.path.join(scriptPath, '..', 'target', 'perf')

    os.system("sdb root on")
    os.system("sdb push %s /root/enable_highlight.sh" % enableHighlightPath)
    os.system("sdb push %s /root/disable_highlight.sh" % disableHighlightPath)
    os.system("sdb push %s /home/owner" % perfPath)


    logging.debug("Enabling Highlight")
    os.system("sdb shell sh /root/enable_highlight.sh")

    logging.debug("Enabled")

    sys.path.append(scriptsPath)
    sys.path.append(swapPath)
    import func_profiling

    try:
        tryCount = 0
        totalTime = 0
        successCount = 0
        result = True
        applicationName = sys.argv[1]
        applicationPath = sys.argv[2]

        applicationDirName = os.path.join(jobDir, "Time_" + applicationName)
        if not os.path.exists(applicationDirName):
            os.mkdir(applicationDirName)

        libs = {}
        call_counts = {}
        i = 0
        startingTimestamp = time.time()
        times["[%s]" % applicationName] = time.time() - startingTimestamp
        times["[%s_SuccessSummary]" % applicationName] = 0
        times["[%s_FailSummary]" % applicationName] = 0

        logging.debug("Preparation phase ended, starting repeatable phase")
        while i < number_or_runs:

            logging.debug("[%s_Run%03d(%d_failed)]" % (applicationName, i, tryCount - i))
            startingTimestamp = time.time()
            tryCount += 1
            if tryCount - 1 >= number_or_runs * 2:

                logging.critical("[%s_Run%03d] Application %s failed to start too many times!" % (applicationName,tryCount - 1,applicationName))
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                raise Exception("[%s_Run%03d] Application %s failed to start too many times!" % (applicationName,tryCount - 1,applicationName))

            reseted_time = time.time()
            if not reboot_device_without_uart():
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                raise Exception("fail to reboot device")


            logging.debug("Rebooting device")
            while wait_time > (time.time() - reseted_time):

                logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                time.sleep(10)

            #os.system("sdb shell dlogutil -c")
            captureCuttingTimeMilliseconds = profile(applicationName, applicationPath)
            if captureCuttingTimeMilliseconds == None:

                logging.critical("[%s_Run%03d] Application %s failed to start!" % (applicationName,tryCount - 1,applicationName))
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                continue

            os.system("sdb shell dlogutil -v threadtime -d > /tmp/log")
            captureCuttingTimeMilliseconds += int(captureCuttingTimeMilliseconds * 0.1) # we add 5% more just for sure

            logging.debug("Cutting capture at %d milliseconds" % captureCuttingTimeMilliseconds)

            i += 1

            logging.debug("Parsing trace...")
            new_libs = parse(captureCuttingTimeMilliseconds)

            logging.debug("len(new_libs) = %d" % len(new_libs))

            logging.debug("new_libs = ")

            logging.debug(new_libs)
            fp = open(os.path.join(applicationDirName, "PerLibConsumption_Run%d.csv" % i), "w")
            currentTotal = 0

            for x in new_libs:
                fp.write("%s %.2f\n" % (x, new_libs[x]))
#                currentTotal += new_libs[x]
                if x in libs.keys():
                    libs[x].append(new_libs[x])
                else:
                    libs[x] = ["None"] * (i-1) + [new_libs[x]]

            fp.close()

            for x in libs:
                if x not in new_libs.keys():
                    libs[x].append("None")


            logging.debug("currentTotal = %d" % (currentTotal))
            times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
            times["[%s_SuccessSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]

            logging.debug("[%s_Run%03d] Ended" % (applicationName, i - 1))

        reseted_time = time.time()
        if not reboot_device_without_uart():
            raise Exception("fail to reboot device")

        os.chdir(jobDir)
        fp = open(os.path.join(applicationDirName, "PerLibConsumption.csv"), "w")
        for lib in libs:
            fp.write("%s" % lib)
            for x in libs[lib]:
                fp.write(" %s" % x)
            fp.write("\n")
#            fp.write("%s %.2f\n" % (lib, libs[lib] / number_or_runs))
#            totalTime += libs[lib] / number_or_runs

        fp.close()

        while wait_time > (time.time() - reseted_time):

            logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
            time.sleep(10)

        try:
            os.remove(os.path.join("/tmp", applicationName))
        except:
            pass

    except Exception as e:

        logging.critical(e)
        result = False
        raise

    finally:
        sp_cmd = [os.path.join(scriptPath, post_processing_exe),\
               "per_lib_time_profiling",\
               "yes" if result else "no",\
               "report.xml",\
               str(applicationName), \
               str(totalTime)]


        sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = sp.communicate()

        os.system("rm /tmp/%s" % applicationName)

        logging.debug("Profiling data")
        for x in sorted(times.keys()):

            logging.debug("%s: %d" % (x, times[x]))


    logging.debug("Disabling Highlight")
    os.system("sdb shell sh /root/disable_highlight.sh")

    logging.debug("Disabled")
    os.chdir(jobDir)
    os.system("rm /tmp/lib*")
    os.system("rm /tmp/ld-*")
    return True


def timeMeasurmentPerf(test_path, target_push_function, target_execute_function,\
        target_execute_function_background, target_execute_function_stdout,\
        target_pull_function, target_reboot_function, color_string, applicationName,\
        applicationPath, result_path, report_file, number_or_runs):

    def profile(app_id, binary_path):
        SLEEP_INTERVAL = 2

        ld_path = os.path.join(os.path.dirname(binary_path)[:-3], "lib")
        fp = open("prepareBinary.sh", "w")
        cmd = "echo 0 > /proc/sys/kernel/kptr_restrict && \
                chmod a+r /proc/kallsyms && \
                echo User > /proc/self/attr/current && \
                su -l owner -c /home/owner/startApplication.sh"
        fp.write(cmd)
        fp.close()

        fp = open("startApplication.sh", "w")
        cmd = "source /etc/profile.d/enlightenment.sh && \
                if [ -f /etc/profile.d/efl.sh ]; then source /etc/profile.d/efl.sh; else source /etc/profile.d/efl_mobile.sh; fi && \
                export LD_LIBRARY_PATH=%s && export AUL_APPID=%s && \
                cd /home/owner && \
                date +\"%%H:%%M:%%S.%%N\" > /tmp/last_timestamp && \
                /home/owner/perf record -F %s %s" % (ld_path, app_id, "15000", binary_path)
        fp.write(cmd)
        fp.close()

        target_push_function("prepareBinary.sh", "/home/owner/prepareBinary.sh")
        target_push_function("startApplication.sh", "/home/owner/startApplication.sh")
        target_execute_function_background("sh /home/owner/prepareBinary.sh")

        timePassed = 0
        time.sleep(SLEEP_INTERVAL)
        timePassed += SLEEP_INTERVAL
        target_pull_function("/tmp/last_timestamp", "/tmp/last_timestamp")
        start_time_str = get_start_of_capture("/tmp/last_timestamp")

        while timePassed < MAX_TRACING_TIME:
            time.sleep(SLEEP_INTERVAL)
            timePassed += SLEEP_INTERVAL

            logging.debug("Getting Applaunch time")
            applicationLaunchDeltaMs = getAppLaunchTime(app_id , start_time_str, target_execute_function_stdout)
            if applicationLaunchDeltaMs != None:
                target_execute_function("killall %s" % binary_path, TEST_TIMEOUT)
                return applicationLaunchDeltaMs


    def parse(cuttingTime):
        target_execute_function("su owner -c \"cd /home/owner && /home/owner/perf report > /tmp/report\"", TEST_TIMEOUT)
        target_pull_function("/tmp/report", "/tmp/report")
        lines = subprocess.check_output(['cat', '/tmp/report']).split('\n')
        libs = {}
        for line in lines:
            splitted = line.split()
            if '#' not in line and len(splitted) != 0:
                libs[splitted[2]] = float(splitted[0][:-1])

        return libs

    post_processing_exe = "post_process_results.py"
    jobDir = os.getcwd()
    wait_time = 30
    report_time = 0

    result = True
    TEST_TIMEOUT = 60
    times = {}

    swapPath = os.path.join(test_path, 'host', 'swap')
    enableHighlightPath = os.path.join(test_path, 'target', 'enable_highlight.sh')
    disableHighlightPath = os.path.join(test_path, 'target', 'disable_highlight.sh')
    perfPath = os.path.join(test_path, 'target', 'perf')

    target_push_function(enableHighlightPath, "/root/enable_highlight.sh")
    target_push_function(disableHighlightPath, "/root/disable_highlight.sh")
    target_push_function(perfPath, "/home/owner/perf")


    logging.debug("Enabling Highlight")
    target_execute_function("sh /root/enable_highlight.sh", TEST_TIMEOUT)

    logging.debug("Enabled")


    logging.debug(color_string("\tdo {} App {}".format(inspect.stack()[0][3], applicationName), fore='red', bold=True))
    try:
        if "No such file" in target_execute_function_stdout("ls %s" % applicationPath):
            raise Exception("Application %s is not installed" % applicationName)

        tryCount = 0
        totalTime = 0
        successCount = 0
        result = True

        applicationDirName = os.path.join(jobDir, "Time_" + applicationName)
        if not os.path.exists(applicationDirName):
            os.mkdir(applicationDirName)

        libs = {}
        call_counts = {}
        i = 0
        cutting_times = []
        startingTimestamp = time.time()
        times["[%s]" % applicationName] = time.time() - startingTimestamp
        times["[%s_SuccessSummary]" % applicationName] = 0
        times["[%s_FailSummary]" % applicationName] = 0

        logging.debug("Preparation phase ended, starting repeatable phase")
        while i < number_or_runs:

            logging.debug("[%s_Run%03d(%d_failed)]" % (applicationName, i, tryCount - i))
            startingTimestamp = time.time()
            tryCount += 1
            if tryCount - 1 >= number_or_runs * 2:

                logging.critical("[%s_Run%03d] Application %s failed to start too many times!" % (applicationName,tryCount - 1,applicationName))
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                raise Exception("[%s_Run%03d] Application %s failed to start too many times!" % (applicationName,tryCount - 1,applicationName))

            reseted_time = time.time()
            if not target_reboot_function():
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                raise Exception("fail to reboot device")


            logging.debug("Rebooting device")
            while wait_time > (time.time() - reseted_time):

                logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                time.sleep(10)

            captureCuttingTimeMilliseconds = profile(applicationName, applicationPath)
            if captureCuttingTimeMilliseconds == None:

                logging.critical("[%s_Run%03d] Application %s failed to start!" % (applicationName,tryCount - 1,applicationName))
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                continue

            target_execute_function("dlogutil -v threadtime -d > /tmp/log", TEST_TIMEOUT)
            cutting_times.append(captureCuttingTimeMilliseconds)
            logging.debug("Cutting capture at %d milliseconds" % captureCuttingTimeMilliseconds)

            i += 1

            logging.debug("Parsing trace...")
            new_libs = parse(captureCuttingTimeMilliseconds)

            logging.debug("len(new_libs) = %d" % len(new_libs))
            logging.debug("new_libs = ")
            logging.debug(new_libs)

            fp = open(os.path.join(applicationDirName, "PerLibConsumption_Run%d.csv" % i), "w")
            currentTotal = sum(new_libs.values())
            normalized_libs = {k: round((v * captureCuttingTimeMilliseconds / currentTotal), 2) for k, v in new_libs.items()}

            for x in normalized_libs:
                fp.write("%s %.2f\n" % (x, normalized_libs[x]))
                if x in libs.keys():
                    libs[x].append(normalized_libs[x])
                else:
                    libs[x] = ["None"] * (i - 1) + [normalized_libs[x]]

            fp.close()

            for x in libs:
                if x not in normalized_libs.keys():
                    libs[x].append("None")


            logging.debug("currentTotal = %.2f", (currentTotal))
            times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
            times["[%s_SuccessSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]

            logging.debug("[%s_Run%03d] Ended" % (applicationName, i - 1))


        os.chdir(jobDir)
        cutting_times.sort()
        report_time = cutting_times[len(cutting_times) / 2]
        fp = open(os.path.join(applicationDirName, "PerLibConsumption.csv"), "w")
        for lib in libs.keys():
            libs[lib].sort()
            median = libs[lib][len(libs[lib]) / 2]
            fp.write("%s %s\n" % (lib, median))

        fp.write("Total %d\n" % report_time)
        fp.close()

        src = applicationDirName
        dest = os.path.join(result_path, os.path.basename(applicationDirName))
        os.system("cp -a %s %s" % (src, dest))

    except Exception as e:
        traceback.print_exc()
        logging.critical(e)
        result = False

    finally:
        sp_cmd = [os.path.join(test_path, "host", post_processing_exe),\
               "per_lib_time_profiling",\
               "yes" if result else "no",\
               report_file,\
               str(applicationName), \
               str(report_time)]


        sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = sp.communicate()

        logging.debug("Profiling data")
        for x in sorted(times.keys()):
            logging.debug("%s: %d" % (x, times[x]))
        os.chdir(jobDir)

    logging.debug("Disabling Highlight")
    target_execute_function("sh /root/disable_highlight.sh", TEST_TIMEOUT)
    logging.debug("Disabled")
    os.chdir(jobDir)
    return True


def memoryMeasurmentSwap(test_path, target_push_function, target_execute_function,
        target_execute_function_background, target_execute_function_stdout,
        target_pull_function, target_reboot_function, color_string, applicationName,
        applicationPath, result_path, report_file, number_or_runs, max_tracing_time):

    jobDir = os.getcwd()
    wait_time = 30
    SLEEP_INTERVAL = 5
    TEST_TIMEOUT = 60
    result = True
    times = {}
    post_processing_exe = "post_process_results.py"
    device = "device"
    totalPersistentMemory = 0
    number_of_try = number_or_runs * 2

    swapPath = os.path.join(test_path, 'host', 'swap')
    scriptsPath = os.path.join(test_path, 'host', 'scripts')
    confFile = os.path.join(test_path, 'host', 'swap', 'conf', 'conf.py')
    instrumentationsFile = os.path.join(test_path, 'host', 'swap', 'conf', 'user_space_inst_list.py')
    enableHighlightPath = os.path.join(test_path, 'target', 'enable_highlight.sh')
    disableHighlightPath = os.path.join(test_path, 'target', 'disable_highlight.sh')

    os.environ['__TRACE_PARCER'] = os.path.join(swapPath, 'trace_parser')
    os.environ['PATH'] = os.environ['PATH'] + ":%s" % (os.environ['__TRACE_PARCER'])

    target_push_function(enableHighlightPath, "/root/enable_highlight.sh")
    target_push_function(disableHighlightPath, "/root/disable_highlight.sh")


    logging.debug("Enabling Highlight")
    target_execute_function("sh /root/enable_highlight.sh", TEST_TIMEOUT)

    logging.debug("Enabled")

    sys.path.append(swapPath)
    import func_profiling
    sys.path.append(scriptsPath)
    import generateNmCache
    import parse_trace

    reseted_time = time.time()
    logging.debug("Rebooting...")
    if not target_reboot_function():
        raise Exception("fail to reboot device")

    while wait_time > (time.time() - reseted_time):
        logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
        time.sleep(10)

    logging.debug(color_string("\tdo {} App {}".format(inspect.stack()[0][3], applicationName), fore='red', bold=True))
    try:
        if "No such file" in target_execute_function_stdout("ls %s" % applicationPath):
            raise Exception("Application %s is not installed" % applicationName)

        tryCount = 0
        totalTime = 0
        successCount = 0
        result = True
        totalPersistentMemory = 0

        libs = {}
        libs['Total'] = []
        call_counts = {}
        i = 0
        startingTimestamp = time.time()
        times["[%s]" % applicationName] = time.time() - startingTimestamp
        times["[%s_SuccessSummary]" % applicationName] = 0
        times["[%s_FailSummary]" % applicationName] = 0

        logging.debug("Preparation phase ended, starting repeatable phase")

        instrumentationsFileString = generateNmCache.generateInstrumentationsConfig(applicationName, applicationPath, memoryProfiling = 1)
        if instrumentationsFileString == None:
            raise Exception("Failed to create instrumentationsFileString")

        os.chdir(scriptsPath)
        applicationDirName = os.path.join(jobDir, "Memory_" + applicationName)
        if not os.path.exists(applicationDirName):
            os.mkdir(applicationDirName)

        os.chdir(swapPath)
        fp = open(instrumentationsFile, "w")
        fp.write(instrumentationsFileString)
        fp.close()
        fp = open(confFile, "w")
        fp.write("""
features = (0x0000000000000000
+ 0x000010000000  #  FL_MEMORY_ALLOC_ALWAYS_PROBING  = //memory allocation API (glibc) always
)

profile_settings = {
 "system_trace_period": 100,
 "data_message_period": 50,
 "enable_probe_type_support": 1,
}
""")
        fp.close()
        swap_parser = parse_trace.SwapParser()

        i = 0
        success_count = 0
        while True:
            logging.debug("Start iteration %.3d for App %s" % (i, applicationName))
            startingTimestamp = time.time()
            if i >= number_of_try:
                logging.critical("Application %s failed to start too many times!" % applicationName)
                raise Exception("Application %s failed to start too many times!" % applicationName)

            os.chdir(swapPath)

            startingTimestamp = time.time()
            applicationLauncingTime = func_profiling.main(device, applicationName, applicationPath,
                    get_start_of_capture, getAppLaunchTime, max_tracing_time, SLEEP_INTERVAL,
                    target_execute_function_stdout, target_execute_function_background,
                    target_push_function, target_pull_function)

            times["[%s_FuncProfiling_Run%.3d]" % (applicationName, i)] = time.time() - startingTimestamp
            startingTimestamp = time.time()
            if applicationLauncingTime == None:
                logging.critical("Application %s failed to start!" % applicationName)
                i += 1
                continue

            trace_file = os.path.join(device, "swap_trace.py")
            new_libs = swap_parser.parse_memory_to_lib_list(trace_file)
            os.chdir(jobDir)
            fp = open(os.path.join(applicationDirName, "PerLibConsumption_Run%03d.csv" %(i)), "w")

            totalPersistentMemory = 0
            totalFreeMemory = 0
            totalTotalMemory = 0
            totalPersistentMemoryCount = 0
            totalFreeMemoryCount = 0
            totalTotalMemoryCount = 0
            total_dict = {}
            for lib in new_libs:
                fp.write("%s %.2f %d %.2f %d %.2f %d\n" % (lib['binary_path'],\
                        lib['pers_size'] / 1024., lib['pers_count'],\
                        lib['free_size'] / 1024., lib['free_count'],\
                        lib['total_size'] / 1024., lib['total_count']))
                totalPersistentMemory += lib['pers_size']
                totalFreeMemory += lib['free_size']
                totalTotalMemory += lib['total_size']
                totalPersistentMemoryCount += lib['pers_count']
                totalFreeMemoryCount += lib['free_count']
                totalTotalMemoryCount += lib['total_count']
                if lib['binary_path'] in libs.keys():
                    libs[lib['binary_path']].append(lib)
                else:
                    libs[lib['binary_path']] = [{'pers_size' : 0, 'pers_count': 0, \
                            'free_size': 0, 'free_count': 0, 'total_size': 0, \
                            'total_count': 0, 'binary_path':lib['binary_path']}]\
                             * success_count + [lib]

            fp.write("Total %.2f %d %.2f %d %.2f %d\n" % (totalPersistentMemory / 1024., totalPersistentMemoryCount,
                                                          totalFreeMemory / 1024., totalFreeMemoryCount,
                                                          totalTotalMemory / 1024., totalTotalMemoryCount))
            fp.close()
            total_dict['binary_path'] = 'Total'
            total_dict['pers_size'] = totalPersistentMemory
            total_dict['pers_count'] = totalPersistentMemoryCount
            total_dict['free_size'] = totalFreeMemory
            total_dict['free_count'] = totalFreeMemoryCount
            total_dict['total_size'] = totalTotalMemory
            total_dict['total_count'] = totalTotalMemoryCount
            libs['Total'].append(total_dict)
            i+=1
            success_count += 1
            times["[%s_ParsingTrace_Run%.3d]" % (applicationName, i)] = time.time() - startingTimestamp

            if success_count >= number_or_runs:
                break

        fp = open(os.path.join(applicationDirName, "PerLibConsumption.csv"), "w")
        for lib_name in libs.keys():
            libs[lib_name].sort(lambda a, b: cmp(a['pers_size'], b['pers_size']))
            median = libs[lib_name][len(libs[lib_name]) / 2]
            if lib_name == 'Total':
                logging.debug("Libs['Total'] =")
                logging.debug(libs[lib_name])
                logging.debug("median total = ")
                logging.debug(median)
                totalPersistentMemory = median['pers_size']
            fp.write("%s %.2f %d %.2f %d %.2f %d\n" % (median['binary_path'],\
                        median['pers_size'] / 1024., median['pers_count'],\
                        median['free_size'] / 1024., median['free_count'],\
                        median['total_size'] / 1024., median['total_count']))

        fp.close()
        src = applicationDirName
        dest = os.path.join(result_path, os.path.basename(applicationDirName))
        os.system("cp -a %s %s" % (src, dest))

    except Exception as e:
        traceback.print_exc()
        logging.critical(e)
        result = False

    finally:

        sp_cmd = [os.path.join(test_path, "host", post_processing_exe),\
               "per_lib_memory_profiling",\
               "yes" if result else "no",\
               report_file,\
               str(applicationName), \
               str(totalPersistentMemory)]

        sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = sp.communicate()
        for x in times.keys():
            logging.debug("%s: %d" % (x, times[x]))
        os.chdir(jobDir)

    logging.debug("Disabling Highlight")
    target_execute_function("sh /root/disable_highlight.sh", TEST_TIMEOUT)

    logging.debug("Disabled")
    os.chdir(jobDir)
    return True


def timeMeasurmentCallgrind(number_or_runs = 1):
    def profile(app_id, binary_path):

        ld_path = os.path.join(os.path.dirname(binary_path)[:-3], "lib")

        fp = open("prepareBinary.sh", "w")
        cmd = "chsmack -e \"User::Pkg::%s\" %s && \
                echo 0 > /proc/sys/kernel/kptr_restrict && \
                chmod a+r /proc/kallsyms && \
                echo System > /proc/self/attr/current && \
                su owner -c /home/owner/startApplication.sh" % (app_id, binary_path)
        fp.write(cmd)
        fp.close()

        fp = open("startApplication.sh", "w")
        cmd = "source /etc/profile.d/enlightenment.sh && \
                source /etc/profile.d/efl.sh && \
                export LD_LIBRARY_PATH=%s && export AUL_APPID=%s && \
                cd /home/owner && valgrind --tool=callgrind --callgrind-out-file=callgrind_output %s" % (ld_path, app_id, binary_path)
        fp.write(cmd)
        fp.close()

        os.system("sdb push prepareBinary.sh /home/owner")
        os.system("sdb push startApplication.sh /home/owner")
        os.system("sdb shell /home/owner/prepareBinary.sh &")
        timePassed = 0
        applicationLaunchDeltaMs = None
        start_time_str = func_profiling.get_start_of_capture()
        while timePassed < MAX_TRACING_TIME:
            time.sleep(SLEEP_INTERVAL)
            timePassed += SLEEP_INTERVAL

            logging.debug("Getting Applaunch time")
            applicationLaunchDeltaMs = func_profiling.getAppLaunchTime(app_id , start_time_str)
            if applicationLaunchDeltaMs != None:
                break

        tryCount = 0
        elapsedTime = 0
        while True:
            if tryCount > 4:
               applicationLaunchDeltaMs = None
               break

            pid = subprocess.check_output(['sdb', 'shell', 'pidof', 'valgrind'])
            if pid == '':
                break
            else:

                logging.debug("waiting for %d seconds try #%d" % (elapsedTime, tryCount))

            os.system("sdb shell kill \`pidof valgrind\`")
            time.sleep(20)
            elapsedTime += 20
            tryCount+=1

        os.system("sdb root off")
        return applicationLaunchDeltaMs

    def parse(cuttingTime):
        os.system("sdb pull /home/owner/callgrind_output")
        lines = subprocess.check_output(['callgrind_annotate', 'callgrind_output']).split('\n')
        libs = {}
        for line in lines:
            if ',' not in line or '[' not in line or ']' not in line:
                continue
            splitted = line.split()
            instructions = splitted[0].replace(",","")
            library = splitted[2].replace("[","").replace("]","")
            if library in libs:
                libs[library] += int(instructions)
            else:
                libs[library] = int(instructions)

        os.remove("callgrind_output")
        return libs

    script_path = os.path.join(os.getcwd(), os.path.dirname(sys.argv[0]), '..')
    post_processing_exe = "post_process_results.py"
    jobDir = os.getcwd()
    wait_time = 30
    os.environ['__TRACE_PARCER'] = os.path.join(script_path, 'swap', 'trace_parser')
    os.environ['PATH'] = os.environ['PATH'] + ":%s" % (os.environ['__TRACE_PARCER'])


    result = True
    TEST_TIMEOUT = 60
    times = {}

    instrumentationsFile = os.path.join(script_path, 'swap', 'conf', 'user_space_inst_list.py')
    confFile = os.path.join(script_path, 'swap', 'conf', 'conf.py')
    scriptsPath = os.path.join(script_path, 'scripts')
    swapPath = os.path.join(script_path, 'swap')
    enableHighlightPath = os.path.join(script_path, '..', 'target', 'enable_highlight.sh')
    disableHighlightPath = os.path.join(script_path, '..', 'target', 'disable_highlight.sh')
    perfPath = os.path.join(script_path, '..', 'target', 'perf')

    os.system("sdb root on")
    os.system("sdb push %s /root/enable_highlight.sh" % enableHighlightPath)
    os.system("sdb push %s /root/disable_highlight.sh" % disableHighlightPath)
    os.system("sdb push %s /home/owner" % perfPath)


    logging.debug("Enabling Highlight")
    os.system("sdb shell sh /root/enable_highlight.sh")

    logging.debug("Enabled")

    sys.path.append(scriptsPath)
    sys.path.append(swapPath)
    import func_profiling

    try:
        totalTime = 0
        result = True
        applicationName = sys.argv[1]
        applicationPath = sys.argv[2]

        applicationDirName = os.path.join(jobDir, "Time_" + applicationName)
        if not os.path.exists(applicationDirName):
            os.mkdir(applicationDirName)

        libs = {}
        call_counts = {}

        i = 0
        tryCount = 0

        startingTimestamp = time.time()
        times["[%s]" % applicationName] = time.time() - startingTimestamp
        times["[%s_SuccessSummary]" % applicationName] = 0
        times["[%s_FailSummary]" % applicationName] = 0

        logging.debug("Preparation phase ended, starting repeatable phase")
        while i < number_or_runs:

            logging.debug("[%s_Run%03d(%d_failed)]" % (applicationName, i, tryCount - i))
            startingTimestamp = time.time()
            tryCount += 1

            reseted_time = time.time()
            if not reboot_device_without_uart():
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                raise Exception("fail to reboot device")


            logging.debug("Rebooting device")
            while wait_time > (time.time() - reseted_time):

                logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
                time.sleep(10)

            #os.system("sdb shell dlogutil -c")
            captureCuttingTimeMilliseconds = profile(applicationName, applicationPath)

            logging.debug("captureCuttingTimeMilliseconds = " + str(captureCuttingTimeMilliseconds))
            if captureCuttingTimeMilliseconds == None:

                logging.critical("[%s_Run%03d] Application %s failed to start!" % (applicationName,tryCount - 1,applicationName))
                times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
                times["[%s_FailSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]
                continue

            os.system("sdb shell dlogutil -v threadtime -d > /tmp/log")
            captureCuttingTimeMilliseconds += int(captureCuttingTimeMilliseconds * 0.1) # we add 5% more just for sure

            logging.debug("Cutting capture at %d milliseconds" % captureCuttingTimeMilliseconds)

            i += 1

            logging.debug("Parsing trace...")
            new_libs = parse(captureCuttingTimeMilliseconds)

            logging.debug("len(new_libs) = %d" % len(new_libs))
            logging.debug("new_libs = ")
            logging.debug(new_libs)
            fp = open(os.path.join(applicationDirName, "PerLibConsumption_Run%d.csv" % i), "w")
            currentTotal = 0
            for x in new_libs:
                fp.write("%s %.2f\n" % (x, new_libs[x]))
                if x in libs.keys():
                    libs[x].append(new_libs[x])
                else:
                    libs[x] = ["None"] * (i-1) + [new_libs[x]]

            fp.close()

            for x in libs:
                if x not in new_libs.keys():
                    libs[x].append("None")


            logging.debug("currentTotal = %d" % (currentTotal))
            times["[%s_Run%03d]" % (applicationName,tryCount - 1)] = time.time() - startingTimestamp
            times["[%s_SuccessSummary]" % applicationName] += times["[%s_Run%03d]" % (applicationName,tryCount - 1)]

            logging.debug("[%s_Run%03d] Ended" % (applicationName, i - 1))

        reseted_time = time.time()
        if not reboot_device_without_uart():
            raise Exception("fail to reboot device")

        os.chdir(jobDir)
        fp = open(os.path.join(applicationDirName, "PerLibConsumption.csv"), "w")
        for lib in libs:
            fp.write("%s" % lib)
            for x in libs[lib]:
                fp.write(" %s" % x)
            fp.write("\n")

        fp.close()

        while wait_time > (time.time() - reseted_time):

            logging.debug("waiting " + str(int(wait_time - (time.time() - reseted_time))) + " sec")
            time.sleep(10)

        try:
            os.remove(os.path.join("/tmp", applicationName))
        except:
            pass

    except Exception as e:
        logging.critical(e)
        result = False
        raise

    finally:
        sp_cmd = [os.path.join(script_path, post_processing_exe),\
               "per_lib_time_profiling",\
               "yes" if result else "no",\
               "report.xml",\
               str(applicationName), \
               str(totalTime)]


        sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = sp.communicate()

        os.system("rm /tmp/%s" % applicationName)

        logging.debug("Profiling data")
        for x in sorted(times.keys()):

            logging.debug("%s: %d" % (x, times[x]))

        logging.debug("Successed: %d Failed: %d" % (i, tryCount - i))
        os.chdir(jobDir)


    logging.debug("Disabling Highlight")
    os.system("sdb shell sh /root/disable_highlight.sh")

    logging.debug("Disabled")
    os.chdir(jobDir)
    os.system("rm /tmp/lib*")
    os.system("rm /tmp/ld-*")
    return True


def main(type = 1):
    if len(sys.argv) < 3 or len(sys.argv) > 4 :
        print "Usage: %s <applicationName> <applicationPath>" % sys.argv[0]
        return False

    applicationName = sys.argv[1]
    applicationPath = sys.argv[2]
    wait_time = int(sys.argv[3])

    script_path = os.path.join(os.getcwd(), os.path.dirname(sys.argv[0]), '..', '..')
    LOG_PATH = "logs"
    loggingFormat = "%(asctime)s - %(levelname)s - %(filename)s - "\
                        "%(lineno)s - %(message)s"

    def initLogging(fname=LOG_PATH + "log.log"):
        if not os.path.exists(LOG_PATH):
            os.mkdir(LOG_PATH)
        logging.basicConfig(filename=fname, level=logging.DEBUG,
                            format=loggingFormat)
        streamHandler = logging.StreamHandler()
        streamHandler.setFormatter(logging.Formatter(loggingFormat))
        logging.getLogger().addHandler(streamHandler)

    def target_reboot():
        wait_time = 30
        os.system("sdb root on")
        os.system("sdb shell reboot")
        time.sleep(wait_time)
        os.system("sdb root on")
        return True

    def target_push_file(src, dest):
        return os.system("sdb push %s %s" % (src, dest))

    def target_execute_cmd_timeout(cmd, timeout):
        timeout = int(timeout)
        testcmd = ["sdb", "shell", cmd]
        p1 = subprocess.Popen(testcmd)
        while timeout > 0:
            if p1.poll() is not None:
                break
            time.sleep(1)
            timeout -= 1
        if timeout == 0 and p1.poll() is None:
            os.kill(p1.pid, signal.SIGTERM)
        return timeout

    def target_execute_cmd_background(cmd):
        testcmd = ["sdb", "shell", cmd]
        def thread_function():
            p1 = subprocess.Popen(testcmd, stdout=subprocess.PIPE).stdout
            data = p1.read()
            p1.close()
            return data

        thread = threading.Thread(target = thread_function)
        thread.setDaemon(True)
        thread.start()

    def target_pull_file(src, dest):
        return os.system("sdb pull %s %s" % (src, dest))

    code = {'reset': '0', 'bold': '1', 'faint': '2', 'italic': '3', 'underline': '4'}
    ground = {'fore': '3', 'back': '4'}
    color = {'black': '0', 'red': '1', 'green': '2', 'yellow': '3', 'blue': '4', 'magenta': '5', 'cyan': '6', 'white': '7'}
    def coded_str(string, **kwargs):
        def coded(v):
            return '\033[' + v + 'm'
        s = ""
        for k in code.keys():
            if k in kwargs and kwargs[k] == True:
                s += coded(code[k])
        for g in ground.keys():
            if g in kwargs:
                s += coded(ground[g] + color[kwargs[g]])

        return s + string + coded(code['reset'])

    def target_execute_cmd_stdout(cmd):
        testcmd = ["sdb", "shell"] + cmd.split()
        p1 = subprocess.Popen(testcmd, stdout=subprocess.PIPE).stdout
        data = p1.read()
        p1.close()
        return data


    if type == 1:
        number_or_runs = 3
        timeMeasurmentSwap(number_or_runs)
    elif type == 2:
        number_or_runs = 1
        if not os.path.exists(os.path.join(os.getcwd(), "results")):
            os.mkdir(os.path.join(os.getcwd(), "results"))
        initLogging()

        timeMeasurmentPerf(script_path, target_push_file,
                target_execute_cmd_timeout, target_execute_cmd_background,
                target_execute_cmd_stdout, target_pull_file, target_reboot,
                coded_str, applicationName, applicationPath,
                os.path.join(os.getcwd(), "results"), os.path.join(os.getcwd(),
                    "report.xml"), number_or_runs)
    elif type == 3:
        timeMeasurmentCallgrind(number_or_runs)
    elif type == 4:
        timeMeasurmentOprofile(number_or_runs)
    elif type == 5:
        number_or_runs = 5
        if not os.path.exists(os.path.join(os.getcwd(), "results")):
            os.mkdir(os.path.join(os.getcwd(), "results"))
        initLogging()

        memoryMeasurmentSwap(script_path, target_push_file,
                target_execute_cmd_timeout, target_execute_cmd_background,
                target_execute_cmd_stdout, target_pull_file, target_reboot,
                coded_str, applicationName, applicationPath,
                os.path.join(os.getcwd(), "results"), os.path.join(os.getcwd(),
                    "report.xml"), number_or_runs, wait_time)


if __name__ == "__main__":
    main(type = 2)
