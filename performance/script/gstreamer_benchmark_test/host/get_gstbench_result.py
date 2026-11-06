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
    Parse the GStreamer benchmark result file and extract per-file average FPS.

    The result file contains a summary table like:
        File                                | Avg FPS   | Min FPS   | Max FPS   | Std Dev
        -----------------------------------------------------------------------
        h264_1000frames_1080p.mp4          | 143.20    | 142.76    | 143.77    | 0.33
        h265_1000frames_4k.h265            | 21.15     | 21.08     | 21.20     | 0.05

    Returns a list of dicts: [{'name': filename, 'fps': str}, ...]
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
                if line.strip().startswith('File') and 'Avg FPS' in line:
                    continue

                # Parse data rows: filename | avg | min | max | std
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        filename = parts[0].strip()
                        fps = parts[1].strip()

                        # Skip empty or separator-only lines
                        if not filename or filename.startswith('-'):
                            continue

                        # Skip N/A values
                        if fps == 'N/A':
                            fps = '0'

                        results.append({
                            'name': filename,
                            'fps': fps
                        })

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        results = None

    return results


def gen_result_str(test_name, test_state, sub_test_name, val):
    """
    Generate a report string for a single video file result.
    Each video file becomes its own test entry (like glbench sub-tests),
    so the DB unique index (job, build, test_name, metric_name) is not violated.
    """
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name': 'GStreamer - ' + sub_test_name, 'executed': 'yes'}

    if test_state != 'success':
        val = 0
    unit = 'fps'

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
    parser.add_argument('result_file', help="path to the GStreamer benchmark result file")
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
            raise Exception("fail to parse GStreamer benchmark results")

        test_state = "success"

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        test_state = "fail"
        data = None
        ret = -1

    finally:
        if data:
            # Write one test entry per video file
            for entry in data:
                result_str = gen_result_str(test_name, test_state, entry['name'], entry['fps'])

                if args.output_file:
                    with open(args.output_file, 'a') as f:
                        f.write(result_str + '\n')

                print(ansi_color_str.coded_str(result_str, fore='green'))
        else:
            # Write a single failure entry
            result_str = gen_result_str(test_name, test_state, 'GStreamer Benchmark', 0)
            if args.output_file:
                with open(args.output_file, 'a') as f:
                    f.write(result_str + '\n')
            print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret


if __name__ == '__main__':
    sys.exit(main())
