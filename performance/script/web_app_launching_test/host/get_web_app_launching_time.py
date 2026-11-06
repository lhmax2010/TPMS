#!/usr/bin/env python3

import os
import sys
import re
import datetime
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

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
# TV (kantsu2e) keyword set: TV web apps are pre-launched via a resident
# wrt-loader, so there is NO "Request cmd(0:APP_START)" caller-side line.
# Observable milestones (verified on 10.0-tv-kantsu2e, basic-webapp.wgt):
#   argv[0] : /opt/usr/apps/<pkgid>/bin/<pkg>   (wrt-loader exec, has pkg)
#   [..:Application:main:done]                   (app_core_ui_base DoRun)
#   lifecycle state changed. <pkg> <pid> CREATED (tvctx-manager)
#   lifecycle state changed. <pkg> <pid> RESUMED (tvctx-manager)
# fallback end: [app state changed] running webapp(app):<pkg>(<pid>)
tv_keyword = [
    "argv[0] : /opt/usr/apps/",
    "Application:main:done",
    "CREATED",
    "RESUMED",
    "[app state changed] running",
]
default_keyword = [
    "Request cmd(0:APP_START)",
    "Application:main:done",
    "Application:create:done",
    "Application:Launching:done",
    "Application:resume:done",
]

def _detect_keyword(result_file):
    """Pick keyword set by probing the dlog file. A TV cold launch DOES
    emit "Request cmd(0:APP_START)", but the chain always breaks at
    create:done (never emitted on TV). Use the default mobile set only
    when the mobile-only milestones actually appear."""
    try:
        # vlog dumps may contain raw bytes from app stdout/stderr that are
        # not valid UTF-8; replace them instead of crashing the whole parse.
        with open(result_file, "r", errors='replace') as f:
            for line in f:
                if line.find("Application:create:done") >= 0 or line.find("Application:reset:done") >= 0:
                    return default_keyword
    except Exception:
        pass
    return tv_keyword

def get_time_data(pkg_name, result_file, keyword=None):

    found_launch = found_main_done = found_create_done = found_reset_done = found_rendered = found_launching_done = False
    dt_launch = dt_to_main = dt_to_create = dt_to_reset = dt_to_rendering = dt_to_launching = None
    to_main = to_create = to_reset = to_launching = to_rendering = to_launching_total = None
    time_dic = {}

    try:
        # Parameterized keyword chain (was hard-coded mobile keywords).
        # In TV mode the milestone lines after launch may belong to other
        # apps too, so pkg_name must appear on every matched line.
        if keyword is None:
            keyword = default_keyword
        tv_mode = keyword is tv_keyword
        with open(result_file, "r", errors='replace') as f:
            for line in f:
                line = line.strip()

                if tv_mode and found_launch and line.find(pkg_name) < 0:
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

                elif found_create_done and not found_launching_done and line.find(keyword[3]) >= 0:
                    dt_to_launching = parse_datetime(line)
                    found_launching_done = True

                # fallback: if Launching:done is not found, use resume:done as fallback
                elif found_create_done and not found_launching_done and line.find(keyword[4]) >= 0:
                    dt_to_launching = parse_datetime(line)
                    found_launching_done = True

        if found_launch:
            to_main = int((dt_to_main - dt_launch).total_seconds() * 1000) if dt_to_main else 0
            to_create = int((dt_to_create - dt_to_main).total_seconds() * 1000) if dt_to_create else 0
            to_launching = int((dt_to_launching - dt_to_create).total_seconds() * 1000) if dt_to_launching else 0
            to_launching_total = (dt_to_launching - dt_launch).total_seconds() if dt_to_launching else 0
        else:
            to_main = to_create = to_reset = to_launching = to_rendering = to_launching_total = 0

        time_dic['to_main'] = to_main
        time_dic['to_create'] = to_create
        time_dic['to_launching'] = to_launching
        time_dic['to_launching_total'] = to_launching_total

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        time_dic = None

    return time_dic

def gen_result_str(test_name, test_state, pkg_info):
    result_list = []
    if pkg_info['result_type'] == 'metrics':
        for r in ['main', 'create', 'launching']:
            to_report = {}
            sub_tag_list = []
            to_report['tag_name'] = 'test'
            to_report['test_name'] = test_name
            to_report['test_state'] = test_state
            to_report['attrs'] = {'name' : 'WebAppLaunching_' + r, 'executed' : 'yes'}

            if test_state == "success":
                key = "to_" + r
                val = pkg_info[key] if key in pkg_info else 0
            else:
                val = 0
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
        to_report['attrs'] = {'name' : 'Web App Launching Time - ' + str(pkg_info['pkg_name']), 'executed' : 'yes'}

        if test_state == "success":
            key = 'to_launching_total'
            val = pkg_info[key] if key in pkg_info else 0
        else:
            val = 0
        unit = 's'

        sub = {}
        sub['tag_name'] = 'metrics'
        sub['attrs'] = {'name' : 'WebAppLaunchingTime', 'val' : str(val), 'unit' : unit, 'isRelevant' : 'true'}
        sub_tag_list.append(sub)

        to_report['sub_tag_list'] = sub_tag_list
        result_list.append(to_report)

    elif pkg_info['result_type'] == 'other':
        pass

    return result_list

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('pkg_list_file', help="tested package list")
    parser.add_argument('result_file_path', help="path to files having each test result")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def main():
    ret = 0
    pkg_list = []

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:

        pkg_list_file = args.pkg_list_file
        result_file_path = args.result_file_path
        test_name = args.test_name

        if not os.path.exists(pkg_list_file):
            raise Exception("package list file does not exist")

        with open(pkg_list_file, 'r') as f:
            for line in f:
                if re.match(r'^#.*', line):
                    continue
                pkg_data = re.split(r'[ \t]+', line.strip())
                pkg_list.append({'pkg_name' : pkg_data[0], 'result_type' : pkg_data[2]})

        for i, pkg in enumerate(pkg_list):

            if not 'pkg_name' in pkg:
                continue

            test_state = ""

            try:
                result_file = os.path.join(result_file_path, "dlog_" + pkg['pkg_name'] + ".txt")

                if not os.path.exists(result_file):
                    raise Exception("no result file")

                time_data = get_time_data(pkg['pkg_name'], result_file,
                                          _detect_keyword(result_file))
                if not time_data:
                    raise Exception("fail to get time data")

                pkg = {**pkg, **time_data}

                test_state = "success"

            except Exception as e:
                print(f"exception: {e}", file=sys.stderr)
                test_state = "fail"

            finally:
                result_str = gen_result_str(test_name, test_state, pkg)

                if args.output_file:
                    with open(args.output_file, 'a') as f:
                        for r in result_str:
                            f.write(str(r) + '\n')

                for r in result_str:
                    print(ansi_color_str.coded_str(str(r), fore='green'))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())

