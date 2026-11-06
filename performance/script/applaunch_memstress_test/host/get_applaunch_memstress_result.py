#!/usr/bin/env python3

import os
import sys
import re
import inspect
import argparse

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def parse_result(input_file):
    data = ""

    try:
        with open(input_file, "r") as f:
            data = f.read()

        data_list = data.split(',')

        lmk = int(data_list[0]) + int(data_list[1])
        reclaimed = int(data_list[2])
        total_elapsed = float(data_list[3])
        resume = int(data_list[5])

        result = [
                    ('LMK', lmk, 'count'),
                    #('RECLAIMED', reclaimed, 'MB')
                    ('ELAPSED', total_elapsed, 'sec'),
                    ('RESUME', resume, 'sec')
                ]

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    finally:
        return result

def gen_result_str(test_name, test_state, data):

    result_list = []
    for d in data:
        to_report = {}
        sub_tag_list = []

        name, val, unit = d
        to_report['tag_name'] = 'test'
        to_report['test_name'] = test_name
        to_report['test_state'] = test_state
        to_report['attrs'] = {'name' : test_name + ' - ' + name, 'executed' : 'yes'}

        sub = {}
        sub['tag_name'] = 'metrics'
        sub['attrs'] = {'name' : name, 'val' : str(val), 'unit' : unit, 'isRelevant' : 'true'}
        sub_tag_list.append(sub)

        to_report['sub_tag_list'] = sub_tag_list

        result_list.append(to_report)

    return result_list

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
    result = ""
    data = None
    test_state = ""

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:
        if args.test_state == "fail":
            raise Exception("failed to test")

        if not os.path.exists(args.input_file):
            raise Exception("input file not exist")

        data = parse_result(args.input_file)
        if not data:
            raise Exception("failed to parse result data")

        test_state = "success"

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        test_state = "fail"
        ret = -1

    finally:
        result_list = gen_result_str(args.test_name, test_state, data)

        if args.output_file:
            with open(args.output_file, 'a') as f:
                for result in result_list:
                    f.write(str(result) + '\n')

        for r in result_list:
            print(ansi_color_str.coded_str(str(r), fore='green'))

    return ret

if __name__ == '__main__':
    sys.exit(main())
