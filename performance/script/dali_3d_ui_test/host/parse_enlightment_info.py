#!/usr/bin/env python3

import os
import sys
import re
import datetime
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def get_average_fps(result_file):
    fps_list = []
    avg = 0.0
    try:
        with open(result_file) as f:
            for line in f:
                m = re.search( '[0-9]+\.[0-9]+', line)
                if m:
                    fps_list.append(m.group())

    except Exception as e:
        print(f"fail to parse result file({result_file}), e={e}", file=sys.stderr)
        fps_list = None
        avg = round(0.0, 1)

        return avg

    try:
        if len(fps_list) < 15:
            raise Exception("not enough result. num of result are {}".format(len(fps_list)))

        while len(fps_list) >= 25:
            fps_list.pop(0)

        for fps in fps_list:
            avg += float(fps)

        avg /= len(fps_list)
        avg = round(avg, 1)

    except Exception as e:
        print(f"fail to get avg, e={e}", file=sys.stderr)
        avg = round(0.0, 1)

    return avg

def gen_result_str(test_name, test_state, val):
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name' : '3D UI Dali', 'executed' : 'yes'}

    if test_state != 'success':
        val = 0
    unit = 'fps'

    sub = {}
    sub['tag_name'] = 'metrics'
    sub['attrs'] = {'name' : 'Dali3DUI', 'val' : str(val), 'unit' : unit, 'isRelevant' : 'true'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)

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
        test_state = args.test_state
        result_file_path = args.result_file_path
        test_name = args.test_name

        if not os.path.exists(pkg_list_file):
            raise Exception("package list file does not exist")

        with open(pkg_list_file, 'r') as f:
            for line in f:
                if re.match(r'^#.*', line):
                    continue

                pkg_list.append(re.split(r'[ \t]+', line.strip())[0])

        for i, pkg in enumerate(pkg_list):

            sub_test_state = ""

            try:
                if test_state != 'success':
                    raise Exception("full test are failed")

                result_file = os.path.join(result_file_path, "enlightenment_info_" + pkg + ".txt")
                if not os.path.exists(result_file):
                    raise Exception("no result file")

                result = get_average_fps(result_file)
                if not result:
                    raise Exception("fail to get fps data")

                sub_test_state = 'success'

            except Exception as e:
                print(f"{e}", file=sys.stderr)
                sub_test_state = "fail"

            finally:
                result_str = gen_result_str(test_name, sub_test_state, result)

                if args.output_file:
                    with open(args.output_file, 'a') as f:
                         f.write(str(result_str) + '\n')

                print(ansi_color_str.coded_str(result_str, fore='green'))

    except Exception as e:
        print(f"{e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())
