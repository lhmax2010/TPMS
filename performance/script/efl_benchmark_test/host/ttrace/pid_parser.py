#!/usr/bin/env python3

import sys, optparse, os, re, subprocess, select

def parse(trace_file_name):
	trace_file = open(trace_file_name, 'r')
	parsed_trace_file_name = trace_file_name.replace('.html.trace.raw', '.ftrace')
	parsed_trace_file = open(parsed_trace_file_name, 'w')
	tid_info={}
	
	ftrace_ptn = re.compile(
		'\s*(.+)-(\d+)' + '\s+\[(\d+)\]' + '\s*(\d+[.]\d+)\:' 
		+ '\s*(\w*)[:]' + '\s*(.*)')
	start_str=False
	for line in trace_file.readlines():
		line=line.replace('\\n\\\n', '\n');
		if start_str is False:
			if line.startswith('# tracer:') is True:
				start_str = True
			else: 
				parsed_trace_file.write(line)
				continue
				
		result = ftrace_ptn.findall(line)
		if(len(result)):
			evt_type = result[0][-2]
			evt_str = result[0][-1]
			cur_t_pid = result[0][1]
			if(result[0][0] == '<...>'): 
				saved_t_name = tid_info.get(cur_t_pid)
				if (saved_t_name != None):
					line = line.replace("<...>", saved_t_name)
					#print 'new: ' + line
			if (evt_type == 'sched_switch'):
				sched_ptn = re.compile("prev_comm=(.*) prev_pid=(\\d+) prev_prio=(\\d+) prev_state=(\\S\\+?|\\S\\|\\S) ==> next_comm=(.*) next_pid=(\\d+) next_prio=(\\d+)");
				sched_evt = sched_ptn.findall(evt_str)
				#print line
				#print sched_evt
				# prev_comm(0), prev_pid(1), prev_prio(2), prev_state(3), next_commm(4), next_pid(5), next_prio(6)
				t_name = sched_evt[0][4]
				t_pid = sched_evt[0][5]
				if (t_name != ''):
					old_t_name = tid_info.get(t_pid)
					if (old_t_name == None or old_t_name != t_name):
						tid_info[t_pid] = t_name
			parsed_trace_file.write(line)
		else:
			parsed_trace_file.write(line)
					
def main():
	trace_file = sys.argv[1]
	parse(trace_file)
	
if __name__ == "__main__":
    main()
