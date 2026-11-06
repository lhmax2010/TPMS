#!/usr/bin/env python3

import os
import sys
import re
import inspect
import argparse
from xml.etree import ElementTree
from xml.dom import minidom

class UsageError(RuntimeError):
    def __init__(self, arg):
       self.args = arg

    def usage(self):
        """docstring for usage"""
        print("usage: {}  INPUT_FILE".format(__file__), file=sys.stderr)


def str_to_dic(s, dic_delim, key_val_delim):
    """docstring for str_to_dic"""
    dic = {}
    fail_flag = False
    try:
        for d in s.split(dic_delim):
            key = val = None
            if len(d) == 0:
                continue
            #print("d={}".format(d))
            '''
            key, val = d.split(key_val_delim)
            key = key.strip()
            val = val.strip()
            '''
            i = d.find(':')
            if i < 0:
                continue
            key = d[:i].strip()
            val = d[i+1:].strip()

            #print("d={}, key={}, val={}".format(d, key, val))
            dic.update({key:val})

            if 'test_state' in dic:
                if dic['test_state'] == 'fail':
                    return dic

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)

    return dic


def convert_dic_arr(inputfile):
    """docstring for convert_dic_arr"""
    result = []
    dic_delim = ','
    key_val_delim = ':'
    temp = None
    try:
        with open(inputfile, 'r') as f:
            try:
                for line in f:
                    line = line.strip()
                    result.append(str_to_dic(line, dic_delim, key_val_delim))
            except Exception as e:
                print(f"exception: {e}", file=sys.stderr)
                result = None
                f.close()

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None
    finally:
        return result


def is_in_list(val, __list):
    ret = False
    for l in __list:
        if val == l:
           return True

    return ret


def is_build_info_result(r, t):
    """docstring for is_build_info_result"""

    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret



def is_booting_time_result(r, t):
    """docstring for is_booting_time_result"""

    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret


def is_memory_usage_test(r, t):
    """docstring for is_memory_usage_test"""

    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret

    ret = False


def is_nand_usage_test(r, t):
    """docstring for is_nand_usage_test"""

    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret


def is_app_launching_test(r, t):
    """docstring for is_app_launching_test"""
    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret


def is_web_app_launching_test(r,t):
    """docstring for is_web_app_launching_test"""
    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret


def is_delim(r, t):
    """docstring for is_delim"""
    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    if "info_name" in r and 'valid_list' in t:
        if is_in_list(r["info_name"], t['valid_list']):
            return True

    return ret

def is_process_memory_usage_test(r, t):
    """docstring for is_process_memory_usage_test"""
    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret

def is_memory_info_test(r, t):
    """docstring for is_memory_info_test"""
    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret


def is_dali_3d_ui_test(r, t):
    """docstring for is_dali_3d_ui_test"""

    ret = False
    name = None
    target_list = None

    '''
    check using test_name
    '''
    if "test_name" in r and 'valid_list' in t:
        if is_in_list(r["test_name"], t['valid_list']):
            return True

    return ret


perfpublisher_xml_list = [
    {
    'valid_list':["booting_time_test"],
    'check_func':is_booting_time_result,
    'test_tag_name':"Booting Time",
    'result_sub_tag_name': "metric",
#    'metric_tag_name':"booting_time",
    'metric_tag_name':"BootingTime",
    'result_sub_tag_attr_isRelevant': "true"
    },
    {
    'valid_list':["memory_usage_test"],
    'check_func':is_memory_usage_test,
    'test_tag_name':"Idle Memory Usage",
    'result_sub_tag_name': "metric",
#    'metric_tag_name':"idle_memory_usage",
    'metric_tag_name':"IdleMemoryUsage",
    'result_sub_tag_attr_isRelevant': "true"
    },
    {
    'valid_list':["nand_usage_test"],
    'check_func':is_nand_usage_test,
    'test_tag_name':"NAND Usage",
    'result_sub_tag_name': "metric",
#    'metric_tag_name':"nand_usage",
    'metric_tag_name':"NANDUsage",
    'result_sub_tag_attr_isRelevant': "true"
    },
    {
    'valid_list':["app_launching_test"],
    'check_func':is_app_launching_test,
    'test_tag_name':"App Launching Time - org.tizen.helloworld",
    'result_sub_tag_name': "metric",
#    'metric_tag_name':"app_launching_time__org_tizen_helloworld",
    'metric_tag_name':"AppLaunchingTime",
    'result_sub_tag_attr_isRelevant': "true"
    },
    {
    'valid_list':["web_app_launching_test"],
    'check_func':is_web_app_launching_test,
    'test_tag_name':"Web App Launching Time - 5OPuG0pfe7.basic",
    'result_sub_tag_name': "metric",
#    'metric_tag_name':"web_app_launching_time__5OPuG0pfe7_basic",
    'metric_tag_name':"WebAppLaunchingTime",
    'result_sub_tag_attr_isRelevant': "true"
    },
    {
    'valid_list':["delim_info"],
    'check_func':is_delim,
    'test_tag_name':"===========================",
    'result_sub_tag_name': "executiontime",
    'result_sub_tag_attr_isRelevant': "false"
    },
    {
    'valid_list':["process_memory_usage_test"],
    'check_func':is_process_memory_usage_test,
    'test_tag_name':"MEMPS - ",
    'result_sub_tag_name': "performance",
    'result_sub_tag_attr_isRelevant': "false"
    },
    {
    'valid_list':["memory_info_test"],
    'check_func':is_memory_info_test,
    'test_tag_name':"MEMINFO",
    'result_sub_tag_name': "performance",
    'result_sub_tag_attr_isRelevant': "false"
    },

    {
    'valid_list':["dali_3d_ui_test"],
    'check_func':is_dali_3d_ui_test,
    'test_tag_name':"3D UI Dali",
    'result_sub_tag_name': "metric",
#    'metric_tag_name':"dali_3d_ui",
    'metric_tag_name':"Dali3DUI",
    'result_sub_tag_attr_isRelevant': "true"
    },
]


def append_perfpublisher_xml_tag(data):
    """docstring for append_perfpublisher_xml_tag"""

    result = []

    for l in data:
        d = dict(l)
        for x in perfpublisher_xml_list:
            if not x['check_func'](d, x):
                continue

            for k, v in x.items():
                 #print"key={}, val={}".format(k,v)
                 d[k] = v

        result.append(d)

    return result


def get_target_info(data):
    """docstring for get_target_info"""
    for d in data:
        dic = dict(d)
        if "target_info" in dic:
            return dic["target_info"]

    return None

def get_report_ver(data):
    """docstring for get_target_info"""
    for d in data:
        dic = dict(d)
        if "report_ver" in dic:
            return dic["report_ver"]

    return None


def gen_perfpublisher_xml2(data):
    """docstring for gen_perfpublisher_xml2"""
    tag_name = None
    text = None
    attr = None
    elem = {}
    test_elem = {'tag':'test', 'attr':{'name':None, 'executed':'yes'}}
    target_elem = {'tag':'target', 'attr':{'threaded':'false'}}
    success_elem = {'tag':'success', 'attr':{'passed':None, 'state':None, 'hasTimedOut':None}}
    result_sub_elem = {'tag': None, 'attr':{'unit':None, 'mesure':None, 'isRelevant':None}}

    target_info = get_target_info(data)

    root = ElementTree.Element("report", name="GeneratedReport-0", categ="GeneratedReport")

    for d in data:
        dic = dict(d)

        if 'test_name' in dic:
            test_name = dic["test_name"]
        else:
            test_name = None

        if test_name == "build_info_test":
            start_tag = ElementTree.SubElement(root, "start")
            elem['tag'] = 'date'
            elem['attr'] = {'format':'YYYYMMDD', 'val':dic['build_id']}
            ElementTree.SubElement(start_tag, elem['tag'], elem['attr'])
            elem['tag'] = 'time'
            elem['attr'] = {'format':'HHMMSS', 'val':dic['build_time']}
            ElementTree.SubElement(start_tag, elem['tag'], elem['attr'])

    for d in data:
        dic = dict(d)

        if 'test_name' in dic:
            test_name = dic["test_name"]
        else:
            test_name = None

        if 'result_sub_tag_name' in dic or 'own_result_sub_tag_name' in dic:

            '''
            if "own_test_tag_name" in dic:
                test_elem['attr']['name'] = dic["own_test_tag_name"]
            else:
                test_elem['attr']['name'] = dic['test_tag_name']
            '''
            test_elem['attr']['name'] = dic["own_test_tag_name"] if "own_test_tag_name" in dic else dic['test_tag_name']
            # test_elem['attr']['executed'] = 'yes' #always 'yes'
            test_tag = ElementTree.SubElement(root, test_elem['tag'], test_elem['attr'])

            targets_tag = ElementTree.SubElement(test_tag, "targets")

            target_tag = ElementTree.SubElement(targets_tag, target_elem['tag'], target_elem['attr']).text = target_info

            result_tag = ElementTree.SubElement(test_tag, "result")

            success_elem['attr']['passed'] = 'yes' if dic['test_state'] == 'success' else 'no'
            success_elem['attr']['state'] = "100" # always "100"??
            success_elem['attr']['hasTimedOut'] = "false" if dic['test_state'] == 'success' else 'true'

            success_tag = ElementTree.SubElement(result_tag, success_elem['tag'], success_elem['attr'])

            parent_tag = result_tag
            if 'result_sub_tag_name' in dic and dic['result_sub_tag_name'] == "metric":
                metrics_tag = ElementTree.SubElement(result_tag, "metrics")
                parent_tag = metrics_tag

            if 'result_sub_tag_name' in dic and dic['result_sub_tag_name'] == "metric":
                result_sub_elem['tag'] = dic['metric_tag_name']
            else:
                result_sub_elem['tag'] = dic['own_result_sub_tag_name'] if 'own_result_sub_tag_name' in dic else dic['result_sub_tag_name']

            result_sub_elem['attr']['unit'] = dic['unit'] if dic['test_state'] == 'success' else ''#TODO
            result_sub_elem['attr']['mesure'] = dic['val'] if dic['test_state'] == 'success' else '0'#TODO
            result_sub_elem['attr']['isRelevant'] = dic['own_result_sub_tag_attr_isRelevant'] if 'own_result_sub_tag_attr_isRelevant' in dic else  dic['result_sub_tag_attr_isRelevant']

            result_sub_tag = ElementTree.SubElement(parent_tag, result_sub_elem['tag'], result_sub_elem['attr'])

    '''
    create xml string
    '''
    rough_string = ElementTree.tostring(root, 'utf-8', method="xml")
    reparsed = minidom.parseString(rough_string)
    xml_string = reparsed.toprettyxml(indent="    ", encoding="UTF-8")

    return xml_string


report_ver_table = [
    {
    'report_ver':'default',
    'append_perfpublisher_xml_tag_func':append_perfpublisher_xml_tag,
    'gen_perfpublisher_xml':gen_perfpublisher_xml2
    },
    {
    'report_ver':"0.1",
    'append_perfpublisher_xml_tag_func':append_perfpublisher_xml_tag,
    'gen_perfpublisher_xml':gen_perfpublisher_xml2
    }
]

def get_func(ver):
    for v in report_ver_table:
        if ver == v['report_ver']:
            return v

    for v in report_ver_table:
        if 'default' == v['report_ver']:
            return v

    return None


def gen_perfpublisher_xml(info, data):

    elem = {}
    root = ElementTree.Element("report", name="GeneratedReport-0", categ="GeneratedReport")

    '''
    setup start tag
    '''
    for r in data:
        if 'tag_name' in r and r['tag_name'] == 'start':
            xml_tag = ElementTree.SubElement(root, r['tag_name'])
            elem = {}
            elem['tag'] = 'date'
            elem['attr'] =  [s for s in r['sub_tag_list'] if s['tag_name'] == 'date'][0]['attrs']
            ElementTree.SubElement(xml_tag, elem['tag'], elem['attr'])
            elem = {}
            elem['tag'] = 'time'
            elem['attr'] = [s for s in r['sub_tag_list'] if s['tag_name'] == 'time'][0]['attrs']
            ElementTree.SubElement(xml_tag, elem['tag'], elem['attr'])


    '''
    fill test data
    '''
    for r in data:
        if 'tag_name' in r and r['tag_name'] == 'test':
#            print("r={}".format(r))
            elem = {}
            elem['tag'] = r['tag_name']
            elem['attr'] = r['attrs']
            test_tag = ElementTree.SubElement(root, elem['tag'], elem['attr'])

            targets_tag = ElementTree.SubElement(test_tag, "targets")

            target_tag = ElementTree.SubElement(targets_tag, 'target', {'threaded' : 'false'}).text = info['target_info']

            result_tag = ElementTree.SubElement(test_tag, "result")

            elem = {}
            elem['tag'] = 'success'
            elem['attr'] = {}
            elem['attr']['passed'] = 'yes' if r['test_state'] == 'success' else 'no'
            elem['attr']['state'] = "100" # always "100"??
            elem['attr']['hasTimedOut'] = "false" if r['test_state'] == 'success' else 'true'

            success_tag = ElementTree.SubElement(result_tag, elem['tag'], elem['attr'])

            p_tag = result_tag
            for s in r['sub_tag_list']:
#                print("s={}".format(s))
                elem = {}
                if s['tag_name'] == 'metrics':
                    p_tag = ElementTree.SubElement(p_tag, s['tag_name'])
                    elem['tag'] = s['attrs']['name']
                    del s['attrs']['name']
                else:
                    elem['tag'] = s['tag_name']

                elem['attr'] = {}
                elem['attr']['mesure'] = s['attrs']['val'] if r['test_state'] == 'success' else '0'
                elem['attr']['unit'] = s['attrs']['unit']
                elem['attr']['isRelevant'] = s['attrs']['isRelevant']
                result_tag = ElementTree.SubElement(p_tag, elem['tag'], elem['attr'])

    '''
    create xml string
    '''
    rough_string = ElementTree.tostring(root, 'utf-8', method="xml")
    reparsed = minidom.parseString(rough_string)
    xml_string = reparsed.toprettyxml(indent="    ", encoding="UTF-8")
    print("{}".format(xml_string))

    return xml_string


def load_result(input_file):
    __info = {}
    __test_result = []

    with open(input_file, "r") as f:
        for l in f:
            dict_l = eval(l)

            if not 'tag_name' in dict_l:
                for k in dict_l.keys():
                    __info[k] = dict_l[k]
                continue

            else:
                __test_result.append(dict_l)

    return __info, __test_result



def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('report_file', help="report file")
    parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
    args = parser.parse_args()

    return args


def main():
    """docstring for main"""
    ret = 0
    info = {}
    test_result = []

    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:
        '''
        load data
        '''
        info, test_result = load_result(args.report_file)
        if not 'report_ver' in info:
            raise Exception("no report ver")

        if not 'target_info' in info:
            raise Exception("no target info")

        result = gen_perfpublisher_xml(info, test_result)

        if args.output_file:
            with open(args.output_file, 'w') as f:
                 f.write(result.decode())

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        result = None

    return ret

if __name__ == '__main__':
    sys.exit(main())
