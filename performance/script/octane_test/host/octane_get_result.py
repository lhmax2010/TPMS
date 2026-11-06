#!/usr/bin/env python3

import os
import sys
import re
import subprocess
import argparse

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('result_file', help="path to files having each test result")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def gen_result_str(test_name, test_state, val):
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name' : 'WebBench - Octane 2.0', 'executed' : 'yes'}

    if test_state != 'success':
        val = 0
    unit = 'score'

    sub = {}
    sub['tag_name'] = 'performance'
    sub['attrs'] = {'val' : str(val), 'unit' : unit, 'isRelevant' : 'false'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)

def main():
    ret = 0
    args = parse_args()

    try:
        result_file = args.result_file
        test_name = args.test_name
        test_state = args.test_state
        result_file_crop = result_file.rsplit(".", 1)[0]+"_crop.png"
        result_file_txt = result_file.rsplit(".", 1)[0]+".txt"

        sp_cmd = ['/usr/bin/convert', result_file, '-crop', '560x390+70+270', result_file_crop]
        sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = sp.communicate()
        if sp.returncode != 0:
            raise Exception('fail to crop result file {}, {}'.format(result_file, __stderr))

        sp_cmd = ['/usr/bin/tesseract', result_file_crop, result_file.rsplit(".", 1)[0], '-l', 'eng']
        sp = subprocess.Popen(sp_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        __stdout, __stderr = sp.communicate()
        if sp.returncode != 0:
            raise Exception('fail to recognize result {}, {}'.format(result_file_crop, __stderr))

        result = None
        valid_result = False
        with open(result_file_txt, "r") as _result_file:
            for line in _result_file:
                if line.startswith("Octane"):
                    valid_result = True
                line = re.sub("[^0-9]", "", line)
                if line.isdigit():
                    result = line

        if valid_result is False or result is None:
            raise Exception('fail to parse result file {}, {}'.format(result_file_txt, __stderr))

        result_str = gen_result_str(test_name, test_state, result)
        if args.output_file:
            with open(args.output_file, 'a') as output_file:
                output_file.write(str(result_str) + '\n')
            print(ansi_color_str.coded_str(result_str, fore='green'))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())
