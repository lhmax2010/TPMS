#!/usr/bin/env python3

import os
import sys
import re
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def parse_used_memory(inputfile):
    result = None

    try:
        with open(inputfile, 'r') as f:
            try:
                for line in f:
                    if line.lower().find("used (mem+swap)") < 0:
                        continue
                    else:
                        line = line.lower().strip()
                        m1 = re.search(r":.*\(", line)
                        result = str(m1.group()).translate(str.maketrans('', '',  r":\)\(")).strip()

            except Exception as e:
                print(f"exception: {e}", file=sys.stderr)
                result = None
                f.close()

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    finally:
        return result

def gen_result_str(test_name, test_state, data, file_name):
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name' : 'Idle Memory Usage', 'executed' : 'yes'}

    if test_state == 'success':
       val, unit = data.split(' ')
       unit = str(unit).upper()
    else:
        val = 0
        unit = 'MB'

    sub = {}
    sub['tag_name'] = 'metrics'
    sub['attrs'] = {'name' : 'IdleMemoryUsage', 'val' : str(val), 'unit' : unit, 'isRelevant' : 'true'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    '''
    in case of, ion shrinked memory result
    '''
    if file_name.find("ion_shrink") > 0:
        to_report['attrs']['name'] +=  ' after ION shrink'
        to_report['sub_tag_list'][0]['tag_name'] = 'performance'
        del to_report['sub_tag_list'][0]['attrs']['name']

    return str(to_report)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true', help='validate before emitting any metrics')
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('input_file', help="file that contain memory data")
    parser.add_argument('-s', "--ion_shrink", help="file that contain memory data after ion shrink")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def main():
    ret = 0
    result = ""
    test_state = ""

    args = parse_args()
    strict = args.strict
    del args.strict  # preserve legacy Namespace logging byte-for-byte
    if strict:
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'standalone'))
        from memory_rigor import parse_memps, parse_kb, SYSTEM_FIELDS
        try:
            if args.test_state != 'success':
                raise ValueError('target collection failed')
            parse_memps(Path(args.input_file).read_text())
            if args.ion_shrink:
                parse_memps(Path(args.ion_shrink).read_text())
        except (ValueError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 1
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    result_files = [args.input_file]

    if args.ion_shrink:
        result_files.append(args.ion_shrink)

    for r in result_files:
        try:
            if args.test_state == "fail":
                raise Exception("failed to test")

            if not os.path.exists(r):
                raise Exception("input file not exist")

            result = parse_used_memory(r)
            if not result:
                raise Exception("fail to parse used memory")

            test_state = "success"

        except Exception as e:
            print(f"exception: {e}", file=sys.stderr)
            test_state = "fail"
            ret = -1

        finally:
            if strict and test_state != "success":
                return ret or 1
            result_str = gen_result_str(args.test_name, test_state, result, r)
            if not result_str:
                raise Exception("fail to generate result string")

            if args.output_file:
                with open(args.output_file, 'a') as f:
                     f.write(result_str + '\n')

            print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret

if __name__ == '__main__':
    sys.exit(main())
