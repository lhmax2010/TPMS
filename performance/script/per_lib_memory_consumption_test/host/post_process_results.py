#!/usr/bin/env python3
import os
import sys

def main(test_name, success, report_file, applicationName, totalPersistentMemory):
    result_file_text = ""
    if os.path.exists(report_file):
        result = open(report_file, "r")
        result_file_text = result.read()
        result.close()

    result = open(report_file, "w")
    result.write(result_file_text)
    result.write("{'tag_name': 'test', 'sub_tag_list': [{'tag_name': 'performance', 'attrs': {'isRelevant': 'false', 'unit': 'KB', 'val': '%.2f'}}], 'test_state': '%s', 'attrs': {'executed': 'yes', 'name': '%s'}, 'test_name': '%s'}\n" % (float(totalPersistentMemory) / 1024., "success" if success == "yes" else "fail", "SABA_MEMORY - " + applicationName + " Persistent memory", test_name))
    result.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]))
