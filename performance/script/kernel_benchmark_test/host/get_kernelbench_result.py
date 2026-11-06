#!/usr/bin/env python3

import os
import sys
import re
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str


def parse_result_file(input_file):
    """
    Parse the kernel benchmark result file and extract all metrics.

    The result file contains raw output from multiple benchmarks:
    - tinymembench: "standard memcpy" and "standard memset" (MB/s)
    - schbench: "average rps" values (4 configurations)
    - ipc-benchmark: "msg/s" values (8 combinations)
    - hackbench: "Time:" values (6 configurations)
    - whetstone: "Whetstones" MIPS
    - dhrystone: "Dhrystones per Second" and "VAX MIPS rating"
    - coremark_multi: "Iterations/Sec"
    - coremark_single: "Iterations/Sec"

    Returns a list of dicts: [{'category': str, 'name': str, 'value': str, 'unit': str}, ...]
    """
    results = []

    try:
        with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # --- tinymembench ---
        # "standard memcpy                                      :   2598.4 MB/s (8.9%)"
        for match in re.finditer(r'standard memcpy\s*:\s*([\d.]+)\s*MB/s', content, re.IGNORECASE):
            results.append({'category': 'tinymembench', 'name': 'standard_memcpy', 'value': match.group(1), 'unit': 'MB/s'})
            break

        for match in re.finditer(r'standard memset\s*:\s*([\d.]+)\s*MB/s', content, re.IGNORECASE):
            results.append({'category': 'tinymembench', 'name': 'standard_memset', 'value': match.group(1), 'unit': 'MB/s'})
            break

        # --- schbench ---
        # Extract "average rps" values in order
        sch_rps_values = re.findall(r'average rps\s*[:=]?\s*([\d.]+)', content, re.IGNORECASE)
        sch_labels = [
            ('schbench_F128_no_locking', 'rps'),
            ('schbench_F256_no_locking', 'rps'),
            ('schbench_F128_locking', 'rps'),
            ('schbench_F256_locking', 'rps'),
        ]
        for i, (label, unit) in enumerate(sch_labels):
            if i < len(sch_rps_values):
                results.append({'category': 'schbench', 'name': label, 'value': sch_rps_values[i], 'unit': unit})

        # --- ipc-benchmark ---
        # Extract msg/s values in order
        ipc_lines = re.findall(r'([\d.]+)\s*msg/s', content, re.IGNORECASE)
        ipc_labels = [
            ('ipc_pipe_512', 'msg/s'),
            ('ipc_pipe_2048', 'msg/s'),
            ('ipc_fifo_512', 'msg/s'),
            ('ipc_fifo_2048', 'msg/s'),
            ('ipc_socket_512', 'msg/s'),
            ('ipc_socket_2048', 'msg/s'),
            ('ipc_tcp_512', 'msg/s'),
            ('ipc_tcp_2048', 'msg/s'),
        ]
        for i, (label, unit) in enumerate(ipc_labels):
            if i < len(ipc_lines):
                results.append({'category': 'ipc-benchmark', 'name': label, 'value': ipc_lines[i], 'unit': unit})

        # --- hackbench ---
        # Extract "Time:" values in order (hackbench output: "Time: 25.992")
        # Must match only lines that start with "Time:" to avoid matching timestamps
        hack_times = re.findall(r'^Time:\s*([\d.]+)', content, re.IGNORECASE | re.MULTILINE)
        hack_labels = [
            ('hackbench_thread_4', 'seconds'),
            ('hackbench_thread_8', 'seconds'),
            ('hackbench_thread_16', 'seconds'),
            ('hackbench_process_4', 'seconds'),
            ('hackbench_process_8', 'seconds'),
            ('hackbench_process_16', 'seconds'),
        ]
        for i, (label, unit) in enumerate(hack_labels):
            if i < len(hack_times):
                results.append({'category': 'hackbench', 'name': label, 'value': hack_times[i], 'unit': unit})

        # --- whetstone ---
        # "C Converted Double Precision Whetstones: 625.0 MIPS"
        match = re.search(r'Whetstones[:\s]+([\d.]+)\s*MIPS', content, re.IGNORECASE)
        if match:
            results.append({'category': 'whetstone', 'name': 'whetstones_mips', 'value': match.group(1), 'unit': 'MIPS'})

        # --- dhrystone ---
        # "Dhrystones per Second: 6982236"
        match = re.search(r'Dhrystones per Second[:\s]+([\d]+)', content, re.IGNORECASE)
        if match:
            results.append({'category': 'dhrystone', 'name': 'dhrystones_per_second', 'value': match.group(1), 'unit': 'Dhrystones/s'})

        # "VAX  MIPS rating = 3973.95"
        match = re.search(r'VAX.*MIPS rating[:\s=]+([\d.]+)', content, re.IGNORECASE)
        if match:
            results.append({'category': 'dhrystone', 'name': 'vax_mips_rating', 'value': match.group(1), 'unit': 'VAX MIPS'})

        # --- coremark_multi ---
        # Find "=== coremark_multi ===" section, then extract first "Iterations/Sec" value
        # Must stop before "=== coremark_single ===" section
        lines = content.split('\n')
        coremark_multi_section = False
        for line in lines:
            if '=== coremark_multi' in line.lower():
                coremark_multi_section = True
                continue
            if '=== coremark_single' in line.lower():
                coremark_multi_section = False
            if coremark_multi_section:
                match = re.search(r'Iterations/Sec\s*[:=]?\s*([\d.]+)', line, re.IGNORECASE)
                if match:
                    results.append({'category': 'coremark_multi', 'name': 'iterations_per_sec', 'value': match.group(1), 'unit': 'Iterations/Sec'})
                    break

        # --- coremark_single ---
        coremark_single_section = False
        for line in lines:
            if '=== coremark_single' in line.lower():
                coremark_single_section = True
                continue
            if coremark_single_section:
                match = re.search(r'Iterations/Sec\s*[:=]?\s*([\d.]+)', line, re.IGNORECASE)
                if match:
                    results.append({'category': 'coremark_single', 'name': 'iterations_per_sec', 'value': match.group(1), 'unit': 'Iterations/Sec'})
                    break

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        results = None

    return results


def gen_result_str(test_name, test_state, sub_test_name, val, unit):
    """
    Generate a report string for a single benchmark metric.
    Each metric becomes its own test entry.
    """
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name': 'Kernel - ' + sub_test_name, 'executed': 'yes'}

    if test_state != 'success':
        val = 0

    sub = {}
    sub['tag_name'] = 'performance'
    sub['attrs'] = {'val': str(val), 'unit': unit, 'isRelevant': 'false'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('result_file', help="path to the kernel benchmark result file")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args


def main():
    ret = 0

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:
        test_name = args.test_name
        test_state = args.test_state
        result_file = args.result_file

        if args.test_state == "fail":
            raise Exception("failed to test")

        if not os.path.exists(result_file):
            raise Exception("result file does not exist: {}".format(result_file))

        data = parse_result_file(result_file)
        if not data:
            raise Exception("fail to parse kernel benchmark results")

        test_state = "success"

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        test_state = "fail"
        data = None
        ret = -1

    finally:
        if data:
            for entry in data:
                sub_test_name = '{}_{}'.format(entry['category'], entry['name'])
                result_str = gen_result_str(test_name, test_state, sub_test_name, entry['value'], entry['unit'])

                if args.output_file:
                    with open(args.output_file, 'a') as f:
                        f.write(result_str + '\n')

                print(ansi_color_str.coded_str(result_str, fore='green'))
        else:
            result_str = gen_result_str(test_name, test_state, 'Kernel Benchmark', 0, '')
            if args.output_file:
                with open(args.output_file, 'a') as f:
                    f.write(result_str + '\n')
            print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret


if __name__ == '__main__':
    sys.exit(main())
