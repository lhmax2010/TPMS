#!/usr/bin/env python3

import os
import sys
import re
import inspect
import datetime
import argparse
import subprocess

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

dlog_keyword = [
	[
		"Request cmd(0:APP_START)",
		"Application:main:done",
		"Application:create:done",
		"Application:reset:done",
		"Application:Launching:done",
		"Application:resume:done"
	],
	[
		"request cmd(0)",
		"Application:main:done",
		"Application:create:done",
		"Application:reset:done",
		"Application:Launching:done",
		"Application:resume:done"
	],

	# Group 2 (TV / kantsu2e): TV apps are pre-launched via a resident
	# loader (wrt-loader for wgt), so there is NO caller-side
	# "Request cmd(0:APP_START)" line. Verified milestones on
	# 10.0-tv-kantsu2e with basic-webapp.wgt:
	#   argv[0] : /opt/usr/apps/<pkgid>/bin/<pkg>   (loader exec, has pkg)
	#   [..:Application:main:done]                   (app_core_ui_base DoRun)
	#   lifecycle state changed. <pkg> <pid> CREATED (tvctx-manager)
	#   lifecycle state changed. <pkg> <pid> RESUMED (tvctx-manager)
	#   [app state changed] running webapp(app):<pkg>(<pid>)
	[
		"argv[0] : /opt/usr/apps/",
		"Application:main:done",
		"CREATED",
		"RESUMED",
		"[app state changed] running",
		"[app state changed] running"
	]
]

old_profiles = ["4.0-mcd-solis", "5.5-mcd-galileo", "6.0-iot-rpi", "6.0-wearable-tw3", "6.5-unified-rpi"]

def _detect_keyword(result_file, profile, old_profiles):
    """Pick keyword group by probing the dlog file. A TV cold launch DOES
    emit "Request cmd(0:APP_START)", but the chain always breaks at
    create:done/reset:done (never emitted on TV). So the mobile groups are
    only usable when those mobile-only milestones actually appear."""
    if profile in old_profiles:
        return dlog_keyword[1]
    try:
        with open(result_file, "r", errors='replace') as f:
            head = f.read()
        if "Application:create:done" in head or "Application:reset:done" in head:
            return dlog_keyword[0]
    except Exception:
        pass
    return dlog_keyword[2]

# value used for phases whose keyword was not found in dlog
INVALID_VAL = 'N/A'

def parse_datetime(log_line):
    # vlog (VD-image) line format:
    #   " 5OPuG0pfe7.basi:  2555.991988890 I/CHROMIUM(P  570, T  570): ..."
    # timestamp is kernel monotonic seconds; wrap it into a datetime so the
    # existing delta math works unchanged.
    m_vlog = re.match(r'^\s*\S+:\s+(\d+\.\d+)\s+[VDIWEA]/', log_line)
    if m_vlog:
        return datetime.datetime(2000, 1, 1) + datetime.timedelta(seconds=float(m_vlog.group(1)))
    r = re.compile(r'[ \t\n\r:\.\+-]+')

    l = r.split(log_line)
    dt = None

    try:
        dt_str = "{}-{} {}:{}:{}.{}".format(l[0], l[1], l[2], l[3], l[4], l[5])
        dt = datetime.datetime.strptime(dt_str, "%m-%d %H:%M:%S.%f")

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        dt = None

    return dt

def get_time_data(pkg_name, result_file, seq, keyword):

    ret = True
    found_launch = found_main_done = found_create_done = found_reset_done = found_launching_done = False
    dt_launch = dt_to_main = dt_to_create = dt_to_reset = dt_to_launching = None
    to_main = to_create = to_reset = to_launching = to_launching_total = None
    time_dic = {}

    try:
        # vlog dumps may contain raw bytes that are not valid UTF-8;
        # replace them instead of crashing the whole parse.
        with open(result_file, "r", errors='replace') as f:
            for line in f:
                line = line.strip()

                # TV mode: CREATED/RESUMED lifecycle lines of OTHER apps also
                # exist in the shared dlog buffer, so require pkg_name on
                # every milestone line once launch has been found.
                if keyword is dlog_keyword[2] and found_launch and line.find(pkg_name) < 0:
                    continue

                if not found_launch and line.find(keyword[0]) >= 0 and line.find(pkg_name) >= 0:
                    dt_launch = parse_datetime(line)
                    found_launch = True

                elif found_launch and not found_main_done and line.find(keyword[1]) >= 0:
                    dt_to_main  = parse_datetime(line)
                    found_main_done = True

                elif found_main_done and not found_create_done and line.find(keyword[2]) >= 0:
                    dt_to_create  = parse_datetime(line)
                    found_create_done = True

                elif (found_create_done if seq == '1st' else found_launch) and not found_reset_done and line.find(keyword[3]) >= 0:
                    dt_to_reset  = parse_datetime(line)
                    found_reset_done = True

                elif found_reset_done and not found_launching_done and line.find(keyword[4]) >= 0:
                    dt_to_launching = parse_datetime(line)
                    found_launching_done = True

                # fallback: if Launching:done is not found, use resume:done as fallback
                elif found_reset_done and not found_launching_done and len(keyword) > 5 and line.find(keyword[5]) >= 0:
                    dt_to_launching = parse_datetime(line)
                    found_launching_done = True

        if found_launch:
            # missing phase keywords are reported as INVALID_VAL, not 0,
            # so that "no log" is never mistaken for "real 0 ms"
            to_main = int((dt_to_main - dt_launch).total_seconds() * 1000) if dt_to_main else INVALID_VAL
            to_create = int((dt_to_create - dt_to_main).total_seconds() * 1000) if dt_to_create else INVALID_VAL
            to_reset = int((dt_to_reset - (dt_to_create if seq == '1st' else dt_launch)).total_seconds() * 1000) if dt_to_reset else INVALID_VAL
            to_launching = int((dt_to_launching - dt_to_reset).total_seconds() * 1000) if dt_to_launching else INVALID_VAL

            # some platforms (e.g. RPi) never emit Launching:done/resume:done;
            # in that case reset:done is the last meaningful milestone, so use it
            # as the launch end instead of declaring the whole run a failure.
            if dt_to_launching:
                to_launching_total = (dt_to_launching - dt_launch).total_seconds()
                ret = True
            elif dt_to_reset:
                to_launching_total = (dt_to_reset - dt_launch).total_seconds()
                ret = True
                print(f"info: {pkg_name} {seq}: no launch-end keyword, using reset:done as end", file=sys.stderr)
            else:
                to_launching_total = INVALID_VAL
                ret = False
        else:
            to_main = to_create = to_reset = to_launching = to_launching_total = INVALID_VAL
            ret = False

        time_dic['to_main'] = to_main
        time_dic['to_create'] = to_create
        time_dic['to_reset'] = to_reset
        time_dic['to_launching'] = to_launching
        time_dic['to_launching_total'] = to_launching_total

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = False
        time_dic = {'to_main': INVALID_VAL, 'to_create': INVALID_VAL, 'to_reset': INVALID_VAL,
                    'to_launching': INVALID_VAL, 'to_launching_total': INVALID_VAL}

    return ret, time_dic

def round3(v):
    int_v = int(round(v))
    if int_v % 2 != 0:
        int_v -= 1

    return int_v

def gen_result_str(test_name, test_state, pkg_info, seq):

    result_list = []
    if pkg_info['result_type'] == 'metrics':
        for r in ['main', 'create', 'reset', 'launching']:
            to_report = {}
            sub_tag_list = []
            to_report['tag_name'] = 'test'
            to_report['test_name'] = test_name
            to_report['test_state'] = test_state
            to_report['attrs'] = {'name' : 'AppLaunching_' + r, 'executed' : 'yes'}

            if test_state == "success":
                key = "to_" + r
                val = pkg_info.get(key, INVALID_VAL)
            else:
                # report INVALID_VAL on failure so a failed measurement is
                # distinguishable from a genuine 0 ms in the report
                val = INVALID_VAL
            unit = 'ms'

            sub = {}
            sub['tag_name'] = 'executiontime'
            sub['attrs'] = {'val' : str(val), 'unit' : unit, 'isRelevant' : 'false'}
            sub_tag_list.append(sub)

            to_report['sub_tag_list'] = sub_tag_list
            result_list.append(to_report)

        to_report = {}
        sub_tag_list = []
        to_report['tag_name'] = 'test'
        to_report['test_name'] = test_name
        to_report['test_state'] = test_state
        to_report['attrs'] = {'name' : 'App Launching Time' + (' 2nd' if seq == '2nd' else '') + ' - ' + str(pkg_info['pkg_name']), 'executed' : 'yes'}

        if test_state == "success":
            val = pkg_info.get('to_launching_total', INVALID_VAL)
        else:
            val = INVALID_VAL
        unit = 's'

        sub = {}
        sub['tag_name'] = 'metrics'
        # Per-round values keep their own names; the headline
        # 'AppLaunchingTime' metric is emitted once per package as the
        # mean of the 1st (cold) and 2nd (warm) rounds.
        sub['attrs'] = {'name' : 'AppLaunchingTime' + ('_2nd' if seq == '2nd' else '_1st'), 'val' : str(val), 'unit' : unit, 'isRelevant' : 'false'}
        sub_tag_list.append(sub)

        to_report['sub_tag_list'] = sub_tag_list
        result_list.append(to_report)

    elif pkg_info['result_type'] == 'other':
        to_report = {}
        sub_tag_list = []
        to_report['tag_name'] = 'test'
        to_report['test_name'] = test_name
        to_report['test_state'] = test_state
        to_report['attrs'] = {'name' : 'App Launching Time'+ (' 2nd' if seq == '2nd' else '') + ' - ' + str(pkg_info['pkg_name']), 'executed' : 'yes'}

        if test_state == "success":
            val1 = pkg_info.get('to_launching_total', INVALID_VAL)
            # bit-packing only works on numbers; a missing phase (N/A) breaks it
            phases = [pkg_info.get('to_reset'), pkg_info.get('to_create'), pkg_info.get('to_main')]
            if all(isinstance(v, (int, float)) for v in phases):
                val2 = round3(phases[0] / 10) << 21 | round3(phases[1] / 10) << 10 | round3(phases[2] / 10)
            else:
                val2 = INVALID_VAL
        else:
            val1 = INVALID_VAL
            val2 = INVALID_VAL

        unit1 = 's'
        unit2 = 'ms'

        sub = {}
        sub['tag_name'] = 'executiontime'
        sub['attrs'] = {'val' : str(val1), 'unit' : unit1, 'isRelevant' : 'false'}
        sub_tag_list.append(sub)

        sub = {}
        sub['tag_name'] = 'compiletime'
        sub['attrs'] = {'val' : str(val2), 'unit' : unit2, 'isRelevant' : 'false'}
        sub_tag_list.append(sub)

        to_report['sub_tag_list'] = sub_tag_list
        result_list.append(to_report)

    else:
        pass

    return result_list

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('pkg_list_file', help="tested package list")
    parser.add_argument('result_file_path', help="path to files having each test result")
    parser.add_argument('profile', help="target system profile")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def main():
    ret = 0
    pkg_list = []
    launching_seq = ['1st', '2nd']

    post_processing_exe2 = "get_app_memory_usage.py"

    script_path = os.path.dirname(sys.argv[0])
    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:

        pkg_list_file = args.pkg_list_file
        result_file_path = args.result_file_path
        test_name = args.test_name
        test_state = args.test_state
        mem_buffer_file = os.path.join(result_file_path, 'mem_buffer_file.txt')
        profile = args.profile

        if not os.path.exists(pkg_list_file):
            raise Exception("package list file does not exist")

        with open(pkg_list_file, 'r') as f:
            for line in f:
                if re.match(r'^#.*', line):
                    continue

                if not line.strip():
                    continue

                pkg_data = re.split(r'[ \t]+', line.strip())
                pkg_list.append({'pkg_name' : pkg_data[0], 'result_type' : pkg_data[2]})


        for seq in launching_seq:
            for i, pkg in enumerate(pkg_list):

                if not 'pkg_name' in pkg:
                    continue

                #ignore 2nd launching of org.tizen.helloworld
                if seq == '2nd' and pkg['pkg_name'] == "org.tizen.helloworld":
                    continue

                test_state = ""

                try:
                    result_file = os.path.join(result_file_path, "dlog_" + seq + "_launch_" + pkg['pkg_name'] + ".txt")

                    if not os.path.exists(result_file):
                        raise Exception("no result file")

                    # Probe the dlog file: TV launches have no caller-side
                    # "Request cmd(0:APP_START)" line, use TV group instead.
                    keyword = _detect_keyword(result_file, profile, old_profiles)
                    # NOTE: don't reuse "ret" here - it is the exit code of main()
                    # and must not be polluted by per-package parse results
                    parse_ok, time_data = get_time_data(pkg['pkg_name'], result_file, seq, keyword)

                    pkg = {**pkg, **time_data}
                    if not parse_ok:
                        raise Exception("fail to get time data")

                    # sanity check: a 2nd launch much faster than the 1st one is
                    # almost always a warm resume (app was only paused), report it
                    if seq == '2nd':
                        first_total = pkg.get('first_total')
                        second_total = pkg.get('to_launching_total')
                        # keep the 2nd-round total for the average metric
                        pkg['second_total'] = second_total
                        pkg_list[i] = pkg
                        if isinstance(first_total, (int, float)) and isinstance(second_total, (int, float)) \
                                and first_total > 0 and second_total > 0 and second_total < first_total * 0.5:
                            print(f"warning: {pkg['pkg_name']} 2nd launch ({second_total}s) < 50% of 1st ({first_total}s), "
                                  "looks like a warm resume", file=sys.stderr)
                    else:
                        pkg['first_total'] = pkg.get('to_launching_total')
                        pkg_list[i] = pkg

                    test_state = "success"

                except Exception as e:
                    print(f"exception: {e}", file=sys.stderr)
                    test_state = "fail"

                finally:
                    result_str = gen_result_str(test_name, test_state, pkg, seq)

                    if args.output_file:
                        with open(args.output_file, 'a') as f:
                            for r in result_str:
                                f.write(str(r) + '\n')

                    for r in result_str:
                        print(ansi_color_str.coded_str(str(r), fore='green'))

                    if seq == '1st':
                        msmps_file = "memps_"+pkg['pkg_name']+".txt"
                        sp_cmd = [os.path.join(script_path, post_processing_exe2),\
                              test_name,\
                              pkg['pkg_name'],\
                              test_state,\
                              os.path.join(result_file_path, msmps_file),\
                              "-o", mem_buffer_file]

                        sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        __stdout, __stderr = sp.communicate()
                        __stdout = __stdout.decode()
                        __stderr = __stderr.decode()

                        print(__stdout)
                        print(__stderr)

        # Headline metric: mean of 1st (cold) and 2nd (warm) launch totals,
        # emitted once per package as 'AppLaunchingTime'. The per-round
        # values are kept as AppLaunchingTime_1st / AppLaunchingTime_2nd.
        for pkg in pkg_list:
            if pkg.get('result_type') != 'metrics':
                continue
            first_total = pkg.get('first_total')
            second_total = pkg.get('second_total')
            if not all(isinstance(v, (int, float)) and v > 0 for v in (first_total, second_total)):
                continue
            avg_val = round((first_total + second_total) / 2, 6)
            to_report = {}
            to_report['tag_name'] = 'test'
            to_report['test_name'] = test_name
            to_report['test_state'] = 'success'
            to_report['attrs'] = {'name' : 'App Launching Time Average - ' + str(pkg['pkg_name']), 'executed' : 'yes'}
            sub = {}
            sub['tag_name'] = 'metrics'
            sub['attrs'] = {'name' : 'AppLaunchingTime', 'val' : str(avg_val), 'unit' : 's', 'isRelevant' : 'true'}
            to_report['sub_tag_list'] = [sub]
            if args.output_file:
                with open(args.output_file, 'a') as f:
                    f.write(str(to_report) + '\n')
            print(ansi_color_str.coded_str(str(to_report), fore='green'))

        if args.output_file:
            # mem_buffer_file is absent when memps is unavailable on the
            # target (TV ships vd_memps only); the timing results above are
            # still valid, so skip the memory section instead of failing.
            if os.path.exists(mem_buffer_file):
                with open(args.output_file, 'a') as f1:
                    for line in open(mem_buffer_file):
                        f1.write(line)

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())
