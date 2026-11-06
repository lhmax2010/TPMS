#!/usr/bin/env python3

import os
import sys
import re
import datetime
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def gen_result_str(test_name, test_state, sub_test_name, val):
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name' : 'GLBench - ' + sub_test_name, 'executed' : 'yes'}

    if test_state != 'success':
        val = 0
    unit = 'fps'

    sub = {}
    sub['tag_name'] = 'performance'
    sub['attrs'] = {'val' : str(val), 'unit' : unit, 'isRelevant' : 'false'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)

def get_fps(input_file):

    fps = None

    with open(input_file, "r") as f:
        for line in f:
            r = re.search(r"GLBenchmark 2.1 .* \(([a-zA-Z0-9.]+) FPS\)", line)
            if r:
                fps = r.group(1)
                break

    return fps

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('pkg_info_file', help="tested package information")
    parser.add_argument('test_info_file', help="tested information (argument, path, ...)")
    parser.add_argument('result_file_path', help="path to files having each test result")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def main():
    ret = 0
    sub_test_list = []

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:
        test_name = args.test_name
        test_state = args.test_state
        pkg_info_file = args.pkg_info_file
        test_info_file = args.test_info_file
        result_file_path = args.result_file_path
        pkg_name = sub_test_name = ""
        sub_test_state = 'fail'
        result = None

        if not os.path.exists(pkg_info_file):
            raise Exception("package info file does not exist")

        if not os.path.exists(test_info_file):
            raise Exception("test list file does not exist")

        with open(pkg_info_file, 'r') as f:
            for line in f:
                if re.match(r'^#.*', line):
                    continue

                pkg_name = re.split(r'[ \t]+', line.strip())[0]
                break

        with open(test_info_file, 'r') as f:
            for line in f:

                if re.match(r'^#.*', line):
                    continue

                try:
                    result = None
                    sub_test_name = re.split(r'[ \t]+', line.strip())[6]
                    result_file = os.path.join(result_file_path, pkg_name + "_" +  sub_test_name + ".txt")

                    result = get_fps(result_file)
                    if not result:
                        raise Exception("fail to get fps data")

                    sub_test_state = 'success'

                except Exception as e:
                    print(f"exception: {e}", file=sys.stderr)
                    sub_test_state = "fail"

                finally:
                    result_str = gen_result_str(test_name, sub_test_state, sub_test_name, result)

                    if args.output_file:
                        with open(args.output_file, 'a') as f:
                             f.write(str(result_str) + '\n')

                    print(ansi_color_str.coded_str(result_str, fore='green'))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())
