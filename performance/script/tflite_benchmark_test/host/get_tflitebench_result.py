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
    Parse the TFLite benchmark result file and extract per-model average inference time.

    The result file contains a summary table like:
        Model                                    | Inference Avg (us)
        ------------------------------------------------------------
        mobilenet_v1_1.0_224.tflite             | 143389
        inception_v4.tflite                     | 2947330

    Returns a list of dicts: [{'name': model_name, 'inference_us': str}, ...]
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
                if line.strip().startswith('Model') and 'Inference' in line:
                    continue

                # Parse data rows: model_name | inference_us
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        model_name = parts[0].strip()
                        inference_us = parts[1].strip()

                        # Skip empty or separator-only lines
                        if not model_name or model_name.startswith('-'):
                            continue

                        # Skip N/A values
                        if inference_us == 'N/A':
                            inference_us = '0'

                        results.append({
                            'name': model_name,
                            'inference_us': inference_us
                        })

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        results = None

    return results


def gen_result_str(test_name, test_state, sub_test_name, val):
    """
    Generate a report string for a single model result.
    Each model becomes its own test entry (like glbench sub-tests),
    so the DB unique index (job, build, test_name, metric_name) is not violated.
    """
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name': 'TFLite - ' + sub_test_name, 'executed': 'yes'}

    if test_state != 'success':
        val = 0
    unit = 'us'

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
    parser.add_argument('result_file', help="path to the TFLite benchmark result file")
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
            raise Exception("fail to parse TFLite benchmark results")

        test_state = "success"

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        test_state = "fail"
        data = None
        ret = -1

    finally:
        if data:
            # Write one test entry per model
            for entry in data:
                result_str = gen_result_str(test_name, test_state, entry['name'], entry['inference_us'])

                if args.output_file:
                    with open(args.output_file, 'a') as f:
                        f.write(result_str + '\n')

                print(ansi_color_str.coded_str(result_str, fore='green'))
        else:
            # Write a single failure entry
            result_str = gen_result_str(test_name, test_state, 'TFLite Benchmark', 0)
            if args.output_file:
                with open(args.output_file, 'a') as f:
                    f.write(result_str + '\n')
            print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret


if __name__ == '__main__':
    sys.exit(main())
