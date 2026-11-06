#!/usr/bin/env python3

import os
import sys
import re
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def get_formatted_data(inputfile):
    result = []
    key_list = []
    dic = {}
    r = re.compile('[ \t]+')
    try:
        with open(inputfile, 'r') as f:
            try:
                for i, line in enumerate(f):
                    line = line.strip()

                    if str.find(line, "=====") >= 0:
                        break

                    #generate key list
                    if i == 0:
                        key_list = r.split(line)
                    else:
                        dic = {}
                        for i, v in enumerate(r.split(line)):
                            dic[key_list[i]] = int(v) if key_list[i] != 'COMMAND' else v

                        result.append(dic)

            except Exception as e:
                print(f"exception: {e}", file=sys.stderr)
                result = None

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    finally:
        if result:
            result = sorted(result, key = lambda x: (x['COMMAND']))

    return result, key_list

def remove_duplicate(data, key_list):
    result = []

    try:
        for i, v in enumerate(data):
            #print "result={}".format(result)
            #print "i={}, v={}".format(i, v)

            if len(result) == 0:
                 result.append(v)
                 continue

            idx = len(result) - 1
            if result[idx]['COMMAND'] == v['COMMAND']:
                for key in key_list:
                    if key == 'PID' or key == 'COMMAND':
                        continue
                    result[idx][key] += v[key]
            else:
                 result.append(v)
                 continue
    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    return result

def cal_memory_usage(data):

    for i, d in enumerate(data):
        total = d['PSS'] + d['3D'] + d['GEM(PSS)']
        data[i]['usage'] = total

    return data

def gen_result_str_org(test_name, data):
    result = ""
    temp = ""
    for i, d in enumerate(data):
        temp = ""
        temp += "test_name: " + test_name
        temp += ", test_state: " + "success"
        temp += ", own_test_tag_name:" + "MEMPS - " + d['COMMAND']
        temp += ","
        temp += "val:" + str(d['usage'])
        temp += ","
        temp += "unit: KB"
        temp +=  "\n"
        result += temp

    return result

def gen_result_str(pkg_name, test_name, data):
    result_list = []

    for i, d in enumerate(data):
        if pkg_name in d['COMMAND']:

            if "com.samsung.w-music-player" in pkg_name:
                if "bin/music-player" not in d['COMMAND']:
                    continue

            to_report = {}
            sub_tag_list = []
            to_report['tag_name'] = 'test'
            to_report['test_name'] = test_name+'2'
            to_report['test_state'] = 'success'
            #to_report['attrs'] = {'name' : 'MEM_USED - ' + d['COMMAND'], 'executed' : 'yes'}
            to_report['attrs'] = {'name' : 'MEM_USED - ' + pkg_name, 'executed' : 'yes'}

            val = d['usage']
            unit = 'KB'

            sub = {}
            sub['tag_name'] = 'performance'
            sub['attrs'] = {'val' : str(val), 'unit' : unit, 'isRelevant' : 'false'}
            sub_tag_list.append(sub)

            to_report['sub_tag_list'] = sub_tag_list

            result_list.append(to_report)
            break

    return result_list

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_name', help="test name")
    parser.add_argument('pkg_name', help="package name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('input_file', help="file that contain build information, generally info.ini")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def gen_excel(result, output_file):
    try:
        import xlsxwriter

        wb = xlsxwriter.Workbook(output_file)
        ws = wb.add_worksheet()
        ws.write('A1', 'COMMAND')
        ws.write('B1', 'PSS')
        ws.write('C1', '3D')
        ws.write('D1', 'GEM(PSS)')
        ws.write('E1', 'GEM(RSS)')

        row = 2
        for d in result:
            ws.write('A' + str(row), d['COMMAND'])
            ws.write('B' + str(row), d['PSS'])
            ws.write('C' + str(row), d['3D'])
            ws.write('D' + str(row), d['GEM(PSS)'])
            ws.write('E' + str(row), d['GEM(RSS)'])
            row = row + 1

        wb.close()
    except ImportError:
        return

def main():
    ret = 0
    result = None
    result_str = ""
    key_list = []

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:

        if args.test_state == "fail":
            raise Exception("failed to test")

        if not os.path.exists(args.input_file):
            raise Exception("input file not exist")

        result, key_list = get_formatted_data(args.input_file)
        if not result:
            raise Exception("fail to parse process memory usage")

        result_path = args.output_file[0:str.rindex(args.output_file, '/') + 1]
        gen_excel(result, result_path + 'memps.xlsx')

        result = remove_duplicate(result, key_list)
        if not result:
            raise Exception("fail to remove duplicate")

        result = cal_memory_usage(result)

        result_str = gen_result_str(args.pkg_name, args.test_name, result)

        if args.output_file:
            with open(args.output_file, 'a') as f:
                for r in result_str:
                    f.write(str(r) + '\n')

        for r in result_str:
            print(ansi_color_str.coded_str(r, fore='green'))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())
