#!/usr/bin/python
import os
import sys
import time
import subprocess
import logging
import re
import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/../../../"))
from client.client import *

sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/../../"))
from library.status import *
from library.environment import *

cl = None
env = None

def main(arg, app_id, binary_path, get_start_of_capture, getAppLaunchTime, \
        MAX_TRACING_TIME, SLEEP_INTERVAL, target_execute_function, \
        target_execute_function_background, target_push_function, target_pull_function):
    global cl, env
    if cl == None:
        cl = Client()
    if env == None:
        env = Environment(cl, arg)

    env.prepare_testing()

    # Connect to target via SWAP protocol
    logging.debug("connecting ...")
    port = cl.Connect()
    if port is None:
        logging.debug("connect to target failed")
        return

    # Run netcat on host
    env.start_nc(port)

    # Add lib profiling
    if cl.send.Add(0) is None:
        exit_fail("msg Add failed")

    # Add kernel probes
    if cl.send.AddKernel() is None:
        exit_fail("msg Add kernel failed")

    # Send config
    if cl.send.Config() is None:
        exit_fail("msg Config failed")

    # Start profiling
    if cl.send.Start(REPLAY_DISABLE) is None:
        exit_fail("msg Start failed")

    # Collecting trace
    logging.debug("Collecting Trace")
    ld_path = os.path.join(os.path.dirname(binary_path)[:-3], "lib")

    fp = open("prepareBinary.sh", "w")
    cmd = "echo User > /proc/self/attr/current && \
            su -l owner -c /home/owner/startApplication.sh"
    fp.write(cmd)
    fp.close()

    fp = open("startApplication.sh", "w")
    cmd = "source /etc/profile.d/enlightenment.sh && \
            if [ -f /etc/profile.d/efl.sh ]; then source /etc/profile.d/efl.sh; else source /etc/profile.d/efl_mobile.sh; fi && \
            export LD_LIBRARY_PATH=%s && export AUL_APPID=%s && \
            date +\"%%H:%%M:%%S.%%N\" > /tmp/last_timestamp && \
            %s" % (ld_path, app_id, binary_path)
    fp.write(cmd)
    fp.close()

    os.system("sdb shell dlogutil -c")
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
        logging.debug("Getting Applaunch time, passed: %d MAX: %d " % (timePassed, MAX_TRACING_TIME))
        applicationLaunchDeltaMs = getAppLaunchTime(app_id , start_time_str, target_execute_function)
        if applicationLaunchDeltaMs != None:
            target_execute_function("killall %s" % binary_path)
            break
    logging.debug("Finishing...")
    if applicationLaunchDeltaMs == None:
        logging.critical("cat /tmp/daemonlog.da:")
        os.system("sdb shell cat /tmp/daemonlog.da")
        logging.critical("dmesg:")
        os.system("sdb shell dmesg")
    try:
        # Stop instrumentation
        if cl.send.Stop() is None:
            exit_fail("msg Stop failed")

        # Close connection
        cl.Disconnect()

        # Stop netcat
        env.stop_nc()

        # Finish testing
        env.finish_testing()
    except Exception as ex:
        logging.critical("Failed to stop SWAP with exception")
        logging.critical(ex)
        applicationLaunchDeltaMs = None

    return applicationLaunchDeltaMs

if __name__ == "__main__":
    main(sys.argv[1])
