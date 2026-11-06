#!/usr/bin/env python3

import os
import sys
import argparse
import re
import xml.etree.ElementTree as et

#append description & change log file

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('src_path', help="source")
    parser.add_argument('dest_path', help="destination")
    args = parser.parse_args()

    return args

def get_version(perfpublisher_xml_file):

    ver = None

    tree = et.parse(perfpublisher_xml_file)
    root = tree.getroot()
    #print root.tag

    for c in root:
        if c.tag != "start":
            continue

        for s in c:
            if s.tag == "date":
                ver = s.attrib.get('val')
                return ver

    return ver

def rearrange_perfpublisher_xml(perfpublisher_xml_file):

    ver = None
    xml_string = None

    tree = et.parse(perfpublisher_xml_file)
    root = tree.getroot()

    for c in root.iter():

        if c.tag == "start":
            for s in c:
                if s.tag == "date":
                    ver = s.attrib.get('val')

        # remove (s), (mb), ...
        elif c.tag == 'test':
            r = re.compile(r'\((s|S|MB|mb)\)')
            if r.search(c.attrib['name']):
                c.attrib['name'] = r.sub("",  c.attrib['name'])

        elif c.tag == 'target' and c.text == 'TM1':
            c.text = '3.0-mobile-tm1'

        elif c.tag == 'BootingTime':
            c.tag = 'booting_time'

        elif c.tag == 'IdleMemoryUsage':
            c.tag = 'idle_memory_usage'

        elif c.tag == 'NANDUsage':
            c.tag = 'nand_usage'

        elif c.tag == 'AppLaunchingTime':
            c.tag = 'app_launching_time__org_tizen_helloworld'

        elif c.tag == 'WebAppLaunchingTime':
            c.tag = 'web_app_launching_time__5OPuG0pfe7_basic'

        elif c.tag == 'Dali3DUI':
            c.tag = 'dali_3d_ui'

        elif 'name' in c.attrib and c.attrib['name'].find('MEMPS') >= 0:
             c.attrib['name'] = c.attrib['name'].replace('MEMPS', 'MemTest')

        elif 'name' in c.attrib and c.attrib['name'].find('MEMINFO') >= 0:
             c.attrib['name'] = c.attrib['name'].replace('MEMINFO', 'MemInfo')

    xml_string = et.tostring(root, 'utf-8', method="xml")

    return ver, xml_string

def replace_buildid(log_file):
    result = ""

    try:
        with open(log_file, 'r') as f:
            for l in f:
                if l.find('BuildVersionZZZ') >= 0:
                    l = l.replace('BuildVersionZZZ :', 'groovy_str_buildid:')
                result += l

        with open(log_file, 'w') as f:
             f.write(result)

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)

def main():

    once = False

    args = parse_args()

    try:
        src = args.src_path if os.path.isabs(args.src_path) else os.path.abspath(args.src_path)
        dest = args.dest_path if os.path.isabs(args.dest_path) else os.path.abspath(args.dest_path)

        print("src={}, dest={}".format(src, dest))

        if not os.path.isabs(src):
            src = os.path.abspath(src)

        # create root of destination
        if not os.path.isabs(dest):
            dest = os.path.abspath(dest)

        if not os.path.exists(dest):
            os.mkdir(dest)

        for buildid_dir in os.listdir(src):

            buildid_dir = os.path.join(src, buildid_dir)
            if not os.path.isabs(buildid_dir):
                buildid_dir = os.path.abspath(buildid_dir)

            if not os.path.isdir(buildid_dir):
                continue

            ver = None
            xml_string = None
            __dest = None

            cur = None
            sub_dir = os.path.join(buildid_dir, 'archive')
            for f in os.listdir(sub_dir):
                cur = os.path.join(sub_dir, f)
                filename = cur.split('/')[-1].lower()

                if filename == "report-0.xml" or filename == "perfpublisher.xml":

                    ver, xml_string = rearrange_perfpublisher_xml(cur)

                    '''
                    if not ver:
                        raise Exception("fail to get version")

                    if not xml_string:
                        raise Exception("fail to get xml string")
                    '''

            if ver and xml_string:
                __dest = os.path.join(dest, ver).strip()

                '''
                create dest dir
                append '-1', '-2', ..., if the result of same version is exist
                '''
                while os.path.exists(__dest):
                    if re.match(r'.*\.[0-9]+$', __dest):
                        __dest += '-1'
                    else:
                        idx = __dest.rfind('-')
                        temp = __dest[idx + 1:]
                        temp = str(int(temp) + 1)
                        __dest = __dest[:idx + 1] +temp

                #create dest dir
                os.mkdir(__dest)

                with open(os.path.join(__dest, "perfpublisher.xml"), "w") as f:
                    f.write(xml_string)

                #copy files
                for sub_dir, dirs, files in os.walk(buildid_dir):
                    for __f in files:
                        __src = os.path.join(sub_dir,__f)

                        if __f == "build.xml":
                            cmd = "cp {} {}".format(__src, os.path.join(__dest, "org.build.xml"))
                            os.system(cmd)

                        elif __f.find(".xml") >= 0:
                            continue

                        elif __f == "log":
                            cmd = "cp {} {}".format(__src, os.path.join(__dest, "org.log"))
                            os.system(cmd)

                            replace_buildid(os.path.join(__dest, "org.log"))

                        else:
                            cmd = "cp {} {}".format(__src, __dest)
                            os.system(cmd)

                print "{}\t->\t{}".format(buildid_dir, __dest)

            once = True

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()
