#!/usr/bin/env python3

import os
import sys
import re
import argparse
import inspect

def get_buildid(inputfile):
    buildid = None
    temp = None

    try:
        with open(inputfile, 'r') as f:
            for line in f:
                line = line.strip().translate(None, ' ;')
                if line.lower().find("build=") >= 0:
                    l = line.lower().find("=") + 1
                    buildid = line[l:]
                    print("buildid={}".format(buildid))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        buildid = None

    return buildid

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', \
                        help="file that contain build information, generally info.ini")
    args = parser.parse_args()

    return args

def gen_groovy_str(buildid):
    groovy_str = "groovy_str_buildid: " + buildid

    return groovy_str

def main():
    ret = 0
    args = parse_args()
    print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

    try:

        if not os.path.exists(args.input_file):
            raise Exception("input file not exist")

        buildid = get_buildid(args.input_file)
        if not buildid:
            raise Exception("fail to get build id")

        print("groovy_str_buildid: {}".format(buildid))

    except Exception as e:
        print(f"exception: {e}", file=sys.stderr)
        ret = -1

    return ret

if __name__ == '__main__':
    sys.exit(main())
