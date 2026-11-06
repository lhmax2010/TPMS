#!/usr/bin/env python3

import os
import sys
import re
import inspect
import datetime
import argparse
import subprocess
import logging

sys.path.append(os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../')), 'lib'))
import ansi_color_str

def parse_efl_bench_result(input_file):
	result = []
	with open(input_file, 'r') as f:
		for line in f:
			if "creation time" in line:
				t = line.split()
				if t.__len__() > 7:
					result.append(("time", t[3], t[7]))
			elif "Evas FPS" in line:
				t = line.split()
				result.append(("fps", t[3], t[8]))

	return result

def gen_report(test_name, test_state, category, name, data, unit):
	to_report = {}
	sub_tag_list = []
	to_report['tag_name'] = 'test'
	to_report['test_name'] = test_name
	to_report['test_state'] = test_state
	to_report['attrs'] = {'name' : category + ' - ' + name, 'executed' : 'yes'}

	sub = {}
	if name is not 'total':
		sub['tag_name'] = 'performance' if category is 'EflScrollFPS' else 'executiontime'
		sub['attrs'] = {'name' : data[1], 'val' : str(data[2]), 'unit' : unit, 'isRelevant' : 'false'}
	else:
		sub['tag_name'] = 'metrics'
		sub['attrs'] = {'name' : 'EflWidgetTime', 'val' : str(data[2]), 'unit' : unit, 'isRelevant' : 'true'}
	sub_tag_list.append(sub)

	to_report['sub_tag_list'] = sub_tag_list
	return to_report

def gen_result_str(test_name, data):
	time_result = ['elm_bg', 'elm_box', 'elm_button', 'elm_check', \
		'elm_conformant', 'elm_datetime', 'elm_entry', 'elm_gengrid', 'elm_genlist', \
		'elm_label', 'elm_layout', 'elm_naviframe', 'elm_progressbar', 'elm_popup', \
		'elm_scroller', 'elm_slider', 'elm_spinner', 'elm_index', 'elm_radio', 'elm_notify', \
		'elm_image', 'elm_panel', 'elm_win']
	fps_result = ['default', '4text', '2text.1icon.1']

	widget_time_sum = 0.0
	result_list = []
	for tr in time_result:
		v = None
		test_state = None

		for d in data:
			if d[0] == "time":
				if d[1] == tr:
					v = d
					break

		if v is not None:
			test_state = 'success'
		else:
			test_state = 'fail'
		to_report = gen_report(test_name, test_state, 'EflWidgetTime', tr, v, 'ms')
		widget_time_sum += float(v[2])
		result_list.append(to_report)

	to_report = gen_report(test_name, test_state, 'EflWidgetTime', 'total', ('time', 'total', widget_time_sum), 'ms')
	result_list.append(to_report)

	for fr in fps_result:
		v = None
		test_state = None

		for d in data:
			if d[0] == "fps":
				if d[1] == fr:
					v = d
					break

		if v is not None:
			test_state = 'success'
		else:
			test_state = 'fail'

		to_report = gen_report(test_name, test_state, 'EflScrollFPS', fr, v, 'fps')
		result_list.append(to_report)

	return result_list

def parse_args():
	parser = argparse.ArgumentParser()
	parser.add_argument('test_name', help="test name")
	parser.add_argument('test_state', help="state of test")
	parser.add_argument('result_file_path', help="path to files having each test result")
	parser.add_argument('-o', "--output_file", metavar='file', help="file to store result")
	args = parser.parse_args()

	return args

def main():
	ret = 0
	result = None
	pkg_list = []
	script_path = os.path.dirname(sys.argv[0])
	args = parse_args()
	print("{} called by {}".format(os.path.abspath(inspect.stack()[0][1]), args))

	try:
		result_file = args.result_file_path

		if not os.path.exists(result_file):
			raise Exception("result file {} is not exist".format(result_file))
		print("start parsing result file")
		result = parse_efl_bench_result(result_file)
		print("end parsing result file")
	except Exception as e:
                print(f"exception: {e}", file=sys.stderr)
		ret = -1
	finally:
		if result is not None:
			result_str = gen_result_str(args.test_name, result)
			if args.output_file:
				with open(args.output_file, 'a') as f:
					for res in result_str:
						f.write(str(res) + '\n')
			for res in result_str:
				print(ansi_color_str.coded_str(res, fore='green'))

	return ret

if __name__ == '__main__':
	sys.exit(main())
