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
    Parse the .NET MicroBenchmarks result file and extract per-case Mean times.

    The result file contains a summary table like:
        Case         | Method  | value        | Mean
        ------------------------------------------------------------------
        Sin          | Sin     |              | 0.123 ns
        Int32_Parse  | Parse   | -2147483648  | 1,052.34 ns
        Int32_Parse  | Parse   | 12345        | 360.67 ns

    The "value" column holds the benchmark parameter for multi-parameter
    cases (may be empty). Returns a list of dicts:
        [{'case': str, 'method': str, 'param': str, 'value': str, 'unit': str}, ...]

    The Mean column is split into a numeric value and a time unit
    (ns, us, ms, s). Thousands separators (",") are stripped from the
    number so "1,052.34 ns" becomes 1052.34. Lower values are faster.
    """
    results = []

    try:
        with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
            in_summary = False
            for line in f:
                line = line.rstrip()

                # Detect start of summary table
                if 'Performance Test Summary' in line:
                    in_summary = True
                    continue

                if not in_summary:
                    continue

                # Skip separator lines
                if re.match(r'^[-]+', line.strip()):
                    continue

                # Skip header line
                if line.strip().startswith('Case') and 'Method' in line:
                    continue

                # Parse data rows: Case | Method | value | Mean
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        case_name = parts[0].strip()
                        method = parts[1].strip()
                        param = parts[2].strip()
                        mean = parts[3].strip()

                        # Skip empty or separator-only lines
                        if not case_name or case_name.startswith('-'):
                            continue

                        # Split mean into numeric value and unit, e.g. "55.85 ns".
                        # Strip thousands separators first so "1,052.34 ns" parses.
                        mean_clean = mean.replace(',', '')
                        m = re.match(r'^([\d.]+)\s*(\S+)$', mean_clean)
                        if m:
                            value = m.group(1)
                            unit = m.group(2)
                        else:
                            # Unparseable (e.g. "N/A")
                            value = '0'
                            unit = ''

                        results.append({
                            'case': case_name,
                            'method': method,
                            'param': param,
                            'value': value,
                            'unit': unit,
                        })

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        results = None

    return results


def gen_result_str(test_name, test_state, sub_test_name, val, unit):
    """
    Generate a report string for a single benchmark case result.
    Each case becomes its own test entry (like glbench sub-tests),
    so the DB unique index (job, build, test_name, metric_name) is not violated.
    """
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name': 'DotNet - ' + sub_test_name, 'executed': 'yes'}

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
    parser.add_argument('result_file', help="path to the .NET benchmark result file")
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
            raise Exception("fail to parse .NET benchmark results")

        test_state = "success"

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        test_state = "fail"
        data = None
        ret = -1

    finally:
        if data:
            # Write one test entry per benchmark row. The parameter ("value"
            # column) is appended when present so multi-parameter cases stay
            # unique in the DB (job, build, test_name, metric_name) index.
            for entry in data:
                if entry.get('param'):
                    sub_test_name = '{}_{}_{}'.format(entry['case'], entry['method'], entry['param'])
                else:
                    sub_test_name = '{}_{}'.format(entry['case'], entry['method'])
                result_str = gen_result_str(test_name, test_state, sub_test_name,
                                            entry['value'], entry['unit'])

                if args.output_file:
                    with open(args.output_file, 'a') as f:
                        f.write(result_str + '\n')

                print(ansi_color_str.coded_str(result_str, fore='green'))
        else:
            # Write a single failure entry
            result_str = gen_result_str(test_name, test_state, 'DotNet Benchmark', 0, '')
            if args.output_file:
                with open(args.output_file, 'a') as f:
                    f.write(result_str + '\n')
            print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret


if __name__ == '__main__':
    sys.exit(main())
