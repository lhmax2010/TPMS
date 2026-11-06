#!/usr/bin/env python3

import os
import sys
import re
import inspect
import argparse

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def parse_systemd_analyze_plot(input_file):
    start = None
    duration = None
    service = None
    result = []
    data = ""

    try:
        with open(input_file, "r") as f:
            data = f.read()

        for l in data.split('\n'):
            re_match1 = re.search("text class", l)
            re_match2 = re.search(r"\(.*\)", l)


            if re_match1 and re_match2:

                '''
                parse start time
                '''
                match = re.search(r"x=\"[+-]?\d+(?:\.\d+)?\"", l)

                if match:
                    start = float(str(match.group()).lstrip("x=\"").rstrip("\""))
                    start /= 100

                '''
                parse service name
                '''
                match = re.search(r">.*\(", l)
                service = match.group().lstrip(">").rstrip("(").strip()


                '''
                parse duration time
                '''
                duration_str = re_match2.group().lstrip("(").rstrip(")")

                # Original code misused rstrip/lstrip (character-set based)
                # and crashed on "Xmin Y.Zs" durations seen on TV targets
                # (e.g. "1min 41.736s" -> ValueError). Parse explicitly:
                # "[<n>min] [<m>s]" | "<m>s" | "<m>ms".
                duration = 0.0
                m = re.match(r"^\s*(?:(\d+(?:\.\d+)?)min)?\s*(?:(\d+(?:\.\d+)?)s)?\s*$", duration_str)
                if m and (m.group(1) or m.group(2)):
                    duration = (float(m.group(1)) if m.group(1) else 0.0) * 60 \
                             + (float(m.group(2)) if m.group(2) else 0.0)
                elif duration_str.endswith("ms"):
                    duration = float(duration_str[:-2]) / 1000

                result.append({'start':start,'service':service,'duration':duration})

    except Exception as e:
        print(f"{e}", file=sys.stderr)
        result = None

    finally:
        return result

def gen_result_str(test_name, test_state, data):
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name' : 'Booting Time', 'executed' : 'yes'}

    if test_state == 'success':
        val = float(data['start']) + float(data['duration'])
        val = "{0:.2f}".format(val)
    else:
        val = 0
    unit = 's'

    sub = {}
    sub['tag_name'] = 'metrics'
    sub['attrs'] = {'name' : 'BootingTime', 'val' : str(val), 'unit' : unit, 'isRelevant' : 'true'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('input_file', help="file that contain build information, generally info.ini")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def main():
    ret = 0
    # TV targets have no boot-animation.service; the VD boot sequence ends
    # with vdtizen-bootseq-idle.service. Use the first marker present so
    # existing targets keep their original behavior.
    animation_services = ["boot-animation.service", "vdtizen-bootseq-idle.service"]
    result = ""
    val = None
    test_state = ""

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:
        if args.test_state == "fail":
            raise Exception("failed to test")

        if not os.path.exists(args.input_file):
            raise Exception("input file not exist")

        plot_data = parse_systemd_analyze_plot(args.input_file)
        if not plot_data:
            raise Exception("failed to parse plot data")

        val = None
        # pick the first boot-completion marker that actually ran
        for svc in animation_services:
            hits = [d for d in plot_data if d['service'] == svc]
            if hits:
                val = hits[0]
                break
        if not val:
             raise Exception("{} is not activated".format(animation_services))

        test_state = "success"

    except Exception as e:
        print(f"{e}", file=sys.stderr)
        test_state = "fail"
        ret = -1

    finally:
        result_str = gen_result_str(args.test_name, test_state, val)

        if args.output_file:
            with open(args.output_file, 'a') as f:
                 f.write(result_str + '\n')

        print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret

if __name__ == '__main__':
    sys.exit(main())
