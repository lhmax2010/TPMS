#!/usr/bin/env python3

import os
import sys
import re
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def parse_build_info(inputfile):
    result = {}
    temp = None
    try:
        with open(inputfile, 'r') as f:
            try:
                for line in f:
                    line = line.strip().translate(str.maketrans('', '', ' ;'))
                    if line.lower().find("build=") >= 0:
                        l = line.lower().find("=") + 1
                        temp = line[l:]
                        result.update({"build_id": temp})
                    elif line.lower().find("date=") >= 0:
                        l = line.lower().find("=") + 1
                        r = line.lower().find("_")
                        temp = line[l:r]
                        result.update({"build_date": temp})
                    elif line.lower().find("time=") >= 0:
                        l = line.lower().find("=") + 1
                        temp = line[l:].replace(":","")
                        result.update({"build_time": temp})

            except Exception as e:
                print(f"exception: {e}", file=sys.stderr)
                result = None
                f.close()

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    finally:
        pass

        return result

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('input_file', \
                        help="file that contain build information, generally info.ini")
    parser.add_argument('-o', "--output_file", metavar='file',
                        help="file to store result")
    args = parser.parse_args()

    return args

def gen_result_str(test_name, test_state, data):
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'start'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state

    if test_state == 'success':
        sub = {}
        sub['tag_name'] = 'date'
        sub['attrs'] = {'format' : 'YYYYMMDD', 'val' : data['build_id']}
        sub_tag_list.append(sub)

        sub = {}
        sub['tag_name'] = 'time'
        sub['attrs'] = {'format' : 'HHMMSS', 'val' : data['build_time']}
        sub_tag_list.append(sub)

        to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)

def main():
    ret = 0
    parsed = ""
    test_state = ""

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:
        if args.test_state == "fail":
            raise Exception("failed to test")

        if not os.path.exists(args.input_file):
            raise Exception("input file not exist")

        parsed = parse_build_info(args.input_file)
        if not parsed:
            raise Exception("fail to parse build info")

        test_state = "success"

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        test_state = "fail"
        ret = -1

    finally:
        result_str = gen_result_str(args.test_name, test_state, parsed)

        if args.output_file:
            with open(args.output_file, 'a') as f:
                 f.write(result_str + '\n')

        print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret

if __name__ == '__main__':
    sys.exit(main())
