#!/usr/bin/env python3

import os
import sys
import re
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def get_package_size(inputfile):
    result = None
    name = None
    size = None
    result = []

    try:
        with open(inputfile, 'r', encoding='utf-8', errors='replace') as f:
            try:
                for line in f:
                    line = line.strip()
                    match = re.search(r"Name\s+:", line)
                    if match:
                        name = str(re.split(r":", line)[1]).strip()

                    match = re.search(r"Size\s+:", line)
                    if match:
                        size = int(str(re.split(r":", line)[1]).strip())

                    if name and size:
                        result.append({'name':name, 'size':size})
                        name = size = None

                result = sorted(result, key = lambda user: (user['name']))
                #result = sorted(result, key = lambda user: (user['size']), reverse=True)

                #print "result={}".format(result)

            except Exception as e:
                print(f"exception: {e}", file=sys.stderr)
                result = None
                f.close()

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    finally:
        if result is not None and len(result) == 0:
            result = None

    return result

def gen_result_str(test_name, test_state, data):
    to_report = {}
    sub_tag_list = []
    to_report['tag_name'] = 'test'
    to_report['test_name'] = test_name
    to_report['test_state'] = test_state
    to_report['attrs'] = {'name' : 'NAND Usage', 'executed' : 'yes'}

    if test_state == 'success':
        __sum = 0
        for d in data:
            __sum += d['size']

        val = float(__sum) / 1024 / 1024
        val = "{0:.2f}".format(val)
    else:
        val = 0
    unit = 'MB'

    sub = {}
    sub['tag_name'] = 'metrics'
    sub['attrs'] = {'name' : 'NANDUsage', 'val' : str(val), 'unit' : unit, 'isRelevant' : 'true'}
    sub_tag_list.append(sub)

    to_report['sub_tag_list'] = sub_tag_list

    return str(to_report)

def gen_xlsx(input_file, output_file):
    result = []
    data = ""
    key_list = []
    valid_key_list = ['Name', 'Size', 'Version', 'Release', 'Architecture',\
                    'Install Date', 'Group', 'License', 'Signature', 'Source RPM',\
                    'Build Date', 'Build Host', 'Relocations', 'Vendor', 'URL',\
                    'VCS', 'Summary', 'Distribution']

    try:
        with open(input_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                match_name = re.match(r'^Name.*:.*', line)
                if match_name:
                    if data == "":
                        data += line
                        continue

                    r = {}
                    key = None
                    val = None

                    for l in data.split('\n'):
                        if len(l) == 0:
                            continue

                        m = re.match(r'^(?P<key>.*?):(?P<val>.*)', l)
                        if m:
                            key = m.group('key').strip()
                            val = m.group('val').strip()
                            if key in valid_key_list:
                                #print("key: {}, val: {}".format(key, val))
                                r[key] = val
                                if not key in key_list:
                                    key_list.append(key)

                    result.append(r)
                    data = ""

                data += line

    except Exception as e:
        print(f"fail to parse {e}", file=sys.stderr)
        result = None

    try:
        import xlsxwriter

        wb = xlsxwriter.Workbook(output_file)
        ws = wb.add_worksheet()

        ws.set_column('A:A', 40)
        ws.set_column('B:B', 15)
        ws.write('A1', 'Name')
        ws.write('B1', 'Size')
        ws.write('C1', 'Version')
        ws.write('D1', 'Release')
        ws.write('E1', 'Architecture')
        ws.write('F1', 'Install Date')
        ws.write('G1', 'Group')
        ws.write('H1', 'License')
        ws.write('I1', 'Signature')
        ws.write('J1', 'Source RPM')
        ws.write('K1', 'Build Date')
        ws.write('L1', 'Build Host')
        ws.write('M1', 'Relocations')
        ws.write('N1', 'Vendor')
        ws.write('O1', 'URL')
        ws.write('P1', 'VCS')
        ws.write('Q1', 'Summary')
        ws.write('R1', 'Distribution')

        row = 2
        for r in sorted(result, key=lambda k: k['Name']):
            ws.write('A' + str(row), r['Name'] if 'Name' in r else "")
            ws.write_number('B' + str(row), int(r['Size']) if 'Size' in r else "")
            ws.write('C' + str(row), r['Version'] if 'Version' in r else "")
            ws.write('D' + str(row), r['Release'] if 'Release' in r else "")
            ws.write('E' + str(row), r['Architecture'] if 'Architecture' in r else "")
            ws.write('F' + str(row), r['Install Date'] if 'Install Date' in r else "")
            ws.write('G' + str(row), r['Group'] if 'Group' in r else "")
            ws.write('H' + str(row), r['License'] if 'License' in r else "")
            ws.write('I' + str(row), r['Signature'] if 'Signature' in r else "")
            ws.write('J' + str(row), r['Source RPM'] if 'Source RPM' in r else "")
            ws.write('K' + str(row), r['Build Date'] if 'Build Date' in r else "")
            ws.write('L' + str(row), r['Build Host'] if 'Build Host' in r else "")
            ws.write('M' + str(row), r['Relocations'] if 'Relocations' in r else "")
            ws.write('N' + str(row), r['Vendor'] if 'Vendor' in r else "")
            ws.write('O' + str(row), r['URL'] if 'URL' in r else "")
            ws.write('P' + str(row), r['VCS'] if 'VCS' in r else "")
            ws.write('Q' + str(row), r['Summary'] if 'Summary' in r else "")
            ws.write('R' + str(row), r['Distribution'] if 'Distribution' in r else "")
            row = row + 1

        wb.close()

    except ImportError as e:
        print(f"xlsxwriter is not installed ({e})", file=sys.stderr)

    except Exception as e:
        print(f"fail to gen xlsx ({e})", file=sys.stderr)
        result = None

    return result

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
    test_state = ""
    val = None

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))
    try:

        if args.test_state == "fail":
            raise Exception("failed to test")

        if not os.path.exists(args.input_file):
            raise Exception("input file not exist")

        val = get_package_size(args.input_file)
        if not val:
            raise Exception("fail to get nand usage")

        result_path = args.output_file[0:str.rindex(args.output_file, '/') + 1]
        gen_xlsx(args.input_file, result_path + "rpm_info.xlsx")

        test_state = "success"

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        test_state = "fail"
        ret = -1

    finally:
        result_str = gen_result_str(args.test_name, test_state, val)

        if args.output_file:
            with open(args.output_file, 'a') as f:
                f.write(result_str + '\n')

        print(ansi_color_str.coded_str(result_str, fore='green'))

    return ret

if __name__ == '__main__':
    sys.exit(main())
