#!/usr/bin/env python3

import os
import sys
import re
import collections
import argparse
import inspect

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

'''
TODO : get below data, physical memory size, automatically
       enable /dev/mem and use dmidecode
'''

target_data = [{'test_target': '3.0-mobile-tm1', 'val': 1024 * 1024, 'unit':'KB'},
               {'test_target': '4.0-mobile-tm1', 'val': 1024 * 1024, 'unit':'KB'},
               {'test_target': '4.0-mobile-tm2', 'val': 3072 * 1024, 'unit':'KB'},
               {'test_target': '3.0-wearable-tw1', 'val': 512 * 1024, 'unit':'KB'},
               {'test_target': '4.0-wearable-tw1', 'val': 512 * 1024, 'unit':'KB'},
               {'test_target': '4.0-wearable-tw2', 'val': 768 * 1024, 'unit':'KB'},
               {'test_target': '5.0-wearable-tw2', 'val': 768 * 1024, 'unit':'KB'},
               {'test_target': '4.0-mcd-solis', 'val': 768 * 1024, 'unit':'KB'},
               {'test_target': '5.5-mcd-galileo', 'val': 768 * 1024, 'unit':'KB'},
               {'test_target': '6.0-iot-rpi', 'val': 4 * 1024 * 1024, 'unit':'KB'},
               {'test_target': '6.5-unified-rpi', 'val': 4 * 1024 * 1024, 'unit':'KB'},
               {'test_target': '7.0-unified-rpi', 'val': 4 * 1024 * 1024, 'unit':'KB'},
               {'test_target': '8.0-unified-rpi', 'val': 4 * 1024 * 1024, 'unit':'KB'},
               {'test_target': '9.0-unified-rpi', 'val': 4 * 1024 * 1024, 'unit':'KB'},
               {'test_target': '9.0-unified-rpi-32bit', 'val': 4 * 1024 * 1024, 'unit':'KB'},
               {'test_target': '10.0-unified-rpi-32bit', 'val': 4 * 1024 * 1024, 'unit':'KB'},
               ]

def parse_memory_info(inputfile):
    result = []
    valid_list = ['MemTotal', 'MemFree', 'Cached', 'Slab', 'KernelStack', 'PageTables']

    try:
        with open(inputfile, 'r') as f:
            for l in f:
                l = l.strip()
                k, v = l.split(":")
                k = k.strip()
                # TV meminfo carries extra multi-value lines (e.g. "zram0:
                # <n> kB OrigDataSize, <n> kB ComprDataSize, ...") which broke
                # the strict 2-token unpack. Take only the first value/unit
                # pair; skip lines that have no unit at all.
                parts = re.split(r'[ \t]+', v.strip())
                if len(parts) < 2:
                    continue
                v, u = parts[0], parts[1]
                if u == 'kB':
                    u = 'KB'
                if k in valid_list:
                    result.append(dict([('unit', u), ('val', v), ('key', k)]))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    finally:
        return result

def parse_vmalloc_info(inputfile):
    n_page = 0
    r = re.compile(r'.+pages=(?P<n_page>\d+).*vmalloc')

    try:
        with open(inputfile, 'r') as f:
            for l in f:
                l = l.strip()
                searched = r.search(l)
                if searched:
                    n_page += int(searched.group('n_page'))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        n_page = 0

    finally:

        result = [dict(unit = 'KB', val = n_page * 4, key = 'VmallocPages')]
        return result

def parse_memps_info(inputfile):
    result = []
    found_delim = False
    found_name = False
    key_list = []
    val_list = []
    valid_list = ['PSS' , '3D', 'GEM(ALLOC)']

    try:
        with open(inputfile, 'r') as f:
            for l in f:
                l = l.strip()

                if found_delim and found_name:
                    val_list = re.split(r'[ \t]+', l)
                    break

                if not found_delim and re.match(r'^=+', l):
                    found_delim = True

                if not found_name and re.match(r'^TOTAL.+', l):
                    key_list = re.split(r'[ \t]+', l.split(':')[1].strip())
                    found_name = True

        for i in range(len(key_list)):
            if key_list[i] in valid_list:
                result.append(dict(unit = 'KB', val = val_list[i], key = key_list[i]))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    finally:

        return result

def arrange_val(test_target, data):

    physical_memory_size = None
    for t in target_data:
        if t['test_target'] == test_target:
            physical_memory_size = t['val']
            break

    if physical_memory_size is not None:
        for i, d in enumerate(data):
            if 'key' in d and d['key'] == 'MemTotal':
                data[i]['val'] = str(physical_memory_size - int(data[i]['val']))

    return data

def gen_result_str(test_name, data):
    result = ""
    result_dic = collections.OrderedDict([('MemTotal', 'MEMINFO_Reserved'),\
                                           ('MemFree', 'MEMINFO_MemFree'),\
                                           ('Cached', 'MEMINFO_Cache'),\
                                           ('Slab', 'MEMINFO_Slab'),\
                                           ('KernelStack', 'MEMINFO_KernelStack'),\
                                           ('PageTables', 'MEMINFO_PageTables'),\
                                           ('VmallocPages', 'MEMINFO_VmallocPages'),\
                                           ('PSS', 'MEMINFO_ProcessPSS'),\
                                           ('3D', 'MEMINFO_3D'),\
                                           ('GEM(ALLOC)', 'MEMINFO_GEM')])
    result_list = []

    for k, own_name in result_dic.items():
        v = None
        test_state = None
        for d in data:
            if d['key'] == k:
                v = d
                break

        if v:
            test_state = 'success'
        else:
            test_state = 'fail'

        to_report = {}
        sub_tag_list = []
        to_report['tag_name'] = 'test'
        to_report['test_name'] = test_name
        to_report['test_state'] = test_state
        to_report['attrs'] = {'name' : own_name, 'executed' : 'yes'}

        sub = {}
        sub['tag_name'] = 'performance'
        sub['attrs'] = {'val' : str(v['val']), 'unit' : v['unit'], 'isRelevant' : 'false'}
        sub_tag_list.append(sub)

        to_report['sub_tag_list'] = sub_tag_list

        result_list.append(to_report)

    return result_list

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true', help='validate before emitting any metrics')
    parser.add_argument('test_name', help="test name")
    parser.add_argument('test_state', help="state of test")
    parser.add_argument('test_target', help="target device of test")
    parser.add_argument('meminfo_file', help="meminfo file including /proc/meminfo")
    parser.add_argument('vmallocinfo_file', help="vmallocinfo file including /proc/vmallocinfo")
    parser.add_argument('memps_file', help="memps file including execution result of memps")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args

def main():
    ret = 0
    result = ""
    test_state = ""
    result_file = {}
    result_str = ""

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
            parse_memps(Path(args.memps_file).read_text())
            parse_kb(Path(args.meminfo_file).read_text(), SYSTEM_FIELDS)
            if not Path(args.vmallocinfo_file).read_text().strip():
                raise ValueError('empty vmallocinfo')
        except (ValueError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 1
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:

        if args.test_state != "success":
            raise Exception("failed to test")

        result_file["meminfo"] = args.meminfo_file
        result_file["vmallocinfo"] = args.vmallocinfo_file
        result_file["memps"] = args.memps_file

        for k, v in result_file.items():
            if not os.path.exists(v):
                raise Exception("result file {} is not exist".format(v))

        result = parse_memory_info(result_file["meminfo"])
        if not result:
            raise Exception("fail to parse used memory")

        temp = parse_vmalloc_info(result_file['vmallocinfo'])
        if not temp:
            raise Exception("fail to parse vmalloc info")
        result += temp

        temp = parse_memps_info(result_file['memps'])
        if not temp:
            raise Exception("fail to parse vmalloc info")
        result += temp

        result = arrange_val(args.test_target, result)
        if not result:
            raise Exception("fail to arrange value")

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    finally:
        if strict and ret != 0:
            return ret
        result_str = gen_result_str(args.test_name, result)
        if args.output_file:
            with open(args.output_file, 'a') as f:
                 for r in result_str:
                     f.write(str(r) + '\n')

        for r in result_str:
            print(ansi_color_str.coded_str(r, fore='green'))

    return ret

if __name__ == '__main__':
    sys.exit(main())
