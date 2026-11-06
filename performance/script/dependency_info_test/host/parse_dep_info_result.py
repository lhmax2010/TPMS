#!/usr/bin/env python3

import os
import sys
import argparse
import inspect

def gen_result_str(test_name, test_state, name, val, executed):
    """ Generate data to result xml """
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name' : name, 'executed' : executed}

    if test_state != 'success':
        val = 0

    sub = {}
    sub['tag_name'] = 'performance'
    sub['attrs'] = {'val' : str(val), 'unit' : 'links', 'isRelevant' : 'false'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)

def parse_args():
    """ Argument parser """
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('result_file_path', help="path to files having each test result")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def main():
    """ main of parse_dep_info_result.py """
    ret = 0
    total_dependencies = 0

    args = parse_args()
    print "{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args)

    test_name = args.test_name
    test_state = args.test_state
    result_file_path = args.result_file_path

    if not os.path.exists(result_file_path):
        raise Exception("Result of dependency_info does not exist")

    try:
        with open(result_file_path, 'r') as result_file:
            for line in result_file:
                line = line.split(',')
                result_str = gen_result_str(test_name, test_state, line[0], line[1], "no")
                total_dependencies = total_dependencies + int(line[1])

                if args.output_file:
                    with open(args.output_file, 'a') as output_file:
                        output_file.write(str(result_str) + '\n')

        result_str = gen_result_str(test_name, test_state,\
                            "Total Library Dependencies", total_dependencies, "yes")
        if args.output_file:
            with open(args.output_file, 'a') as output_file:
                output_file.write(str(result_str) + '\n')

    except IOError as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())
