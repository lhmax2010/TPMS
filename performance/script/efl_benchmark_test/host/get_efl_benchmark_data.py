import os
import subprocess
import re
import sys
import logging

# 0 means stand-alone, 1 means run by TPMS
runmode = 0

def printlog(str):
	if runmode == 0:
		print(str)
	else:
		logging.debug(str)

def get_ini(command):
    stream = os.popen(command)
    output = stream.read()
    printlog(output)
    out = output.split()
    out[2] = out[2].replace('Build=', '')
    printlog("=================================================================================")
    printlog("")
    printlog("                           - EFL BENCHMARK START -                               ")
    printlog("")
    printlog("=================================================================================")
    printlog("")
    printlog("Target Binary = " + out[2])
    printlog("")

def run_command(command):
    stream = os.popen(command)
    output = stream.read()
    printlog(output)

def run_get_log(cmd, outfile):
    command_list = cmd.split(" ")
    proc = subprocess.Popen(command_list,
                            stdout = subprocess.PIPE,
                            stderr = subprocess.PIPE,
                            universal_newlines = True,
                            )
    stdout = []
    while proc.poll() is None:
        line = proc.stdout.readline()
        printlog(line)
        outfile.write(line)
        filter = re.search(r"TPMS Trace Start", line)
        if (filter):
            break
    proc.terminate()

def do_benchmark(mode = 1, rpm_dir = None, script_dir = None, result_dir = None, serial = None):
	#Start scrip here
	runmode = mode
	result_file = result_dir + "/efl_bench_result.txt"
	result = open(result_file, "w")
	if serial is not None:
		sdb_cmd_prefix = "sdb -s " + serial + " "
	else:
		sdb_cmd_prefix = "sdb "

	#Print target binary info
	try:
		get_ini(sdb_cmd_prefix + "shell cat /etc/info.ini")

		#rpm install in target
		printlog("                           - RPM INSTALL START -                               ")
		run_command(sdb_cmd_prefix + "root on")
		run_command(sdb_cmd_prefix + "shell mount -o rw,remount /")
		run_command(sdb_cmd_prefix + "push " + rpm_dir + "/org.tizen.efl-benchmark-tizen-wearable-0.1-1.armv7l.rpm /home")
		run_command(sdb_cmd_prefix + "shell rpm -Uvh --force --nodeps /home/org.tizen.efl-benchmark-tizen-wearable-0.1-1.armv7l.rpm")
		printlog("                           - RPM INSTALL FINISH -                              ")

		#Clean up dlog before read
		run_command(sdb_cmd_prefix + "shell dlogutil -c")

		#Benchmark App Start
		printlog("                           - Sample App Start -                               ")

		#Display on
		run_command(sdb_cmd_prefix + "shell devicectl display stop")

		run_command(sdb_cmd_prefix + "shell launch_app org.tizen.efl-benchmark-tizen-wearable")
		run_get_log(sdb_cmd_prefix + "shell dlogutil EFL-BENCHMARK", result)

		#Trace Start
		run_command(script_dir + "/ttrace/./ttrace.py -b 20480 -o " + result_dir + "/benchmark.html -t 5 input view gfx am wm web efl app sched freq")
		printlog("                           - EFL BENCHMARK FINISH -                               ")
		run_command("stty sane")
	except:
		logging.debug("error occurred")
		result.close()
		return False
	finally:
		result.close()
		return True

if __name__ == "__main__":
	do_benchmark(mode = 0, rpm_dir = os.getcwd(), script_dir = os.getcwd(), result_dir = os.getcwd())
