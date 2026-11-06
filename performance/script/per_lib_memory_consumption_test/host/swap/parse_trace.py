#!/usr/bin/python

import sys
import argparse
import xml.etree.cElementTree as ET
import logging

MSG_ENTRY   = 0x00008
MSG_EXIT    = 0x00009

MSG_MEM_BIN = 0x00012
MSG_MEM_EVT = 0x00101
MSG_PROCESS_INFO_STR = "'msg_id': 0x00001"
processed_mem_msgs = {MSG_MEM_BIN, MSG_MEM_EVT}

mem_alloc_funcs = {'malloc', 'calloc', 'new', 'posix_memalign', 'strdup'}
mem_ignore_funcs = {'memcmp'}
mem_free_funcs = {'free', 'delete'}
mem_realloc_funcs = {'realloc'}

processed_msgs = {MSG_ENTRY, MSG_EXIT}

# trace files types:
TRACE_FUNCTIONS = 0x00001
TRACE_MEMORY    = 0x00002

print_errors = False
print_libraries = False

def print_err(string):
    if print_errors:
        logging.critical(string)

class SwapParser(object):
    def __init__(self, trace_type = TRACE_FUNCTIONS, trace_time = 0):
        self.pending_item_list = []
        self.libs_dict = {}
        self.trace_start = 0
        self.stop_flag = False
        self.trace_time = trace_time
        self.trace_file = './swap_trace.py'
        self.trace_type = trace_type

    def parse_trace_file(self, trace_file=None):
        if trace_file == None:
            trace_file = self.trace_file

        if self.trace_type == TRACE_FUNCTIONS:
            self.parse_trace_file_to_tree(trace_file)
        elif self.trace_type == TRACE_MEMORY:
            self.parse_trace_file_mem(trace_file)

    def parse_trace_file_mem(self, trace_file = None):
        self.trace_mem = TraceMem()

        if trace_file == None:
            trace_file = self.trace_file

        line_buffer = ''
        with open(trace_file) as f:
            for line in f:
                if MSG_PROCESS_INFO_STR in line:
                    self.trace_mem.parse_process_info_str(line)
                    continue

                line = line_buffer + line
                if 'msg_id' in line and line.count('{') != line.count('}'):
                    line_buffer += line
                    continue
                else:
                    line_buffer = ''
                msg = self.parse_line(line)
                if msg != None:
                    self.trace_mem.process_msg(msg)

    def parse_trace_file_to_tree(self, trace_file=None, trace_time=0):
        if trace_time == 0:
            trace_time = self.trace_time
        self.trace_tree = TraceTree(trace_time)

        if trace_file == None:
            trace_file = self.trace_file

        with open(trace_file) as f:
            for line in f:
                msg = self.parse_line(line)
                if msg != None:
                    self.trace_tree.process_msg(msg)
                #if self.stop_flag:
                #    f.close()
                #    return

    def parse_to_lib_dict(self, trace_file=None, trace_time=0):
        self.parse_trace_file_to_tree(trace_file, trace_time)
        self.trace_tree.count_self_times_for_tree()
        self.trace_tree.make_libs_dictionary()
        return self.trace_tree.libs_dict

    def parse_memory_to_lib_list(self, trace_file=None):
        self.parse_trace_file_mem(trace_file)
        self.trace_mem.count_persistent_mem()
        return self.trace_mem.libs_list

    def parse_line(self, line):
        string_dict = {}
        line = line.translate(None, " {}'\n")
        line_list = line.split(",")
        for dict_item_str in line_list:
            if ":" in dict_item_str:
                dict_item_list = dict_item_str.split(":")
                try:
                    string_dict[dict_item_list[0]] = int(dict_item_list[1], 0)
                except:
                    string_dict[dict_item_list[0]] = dict_item_list[1]
        return string_dict

    # UNUSED
    def string_dict_to_msg(self, string_dict):
        if string_dict['msg_id'] in processed_msgs:
            trace_msg = TraceMsg()
            trace_msg.fill(string_dict['msg_id'], string_dict['time'], string_dict['tid'],
                    string_dict['pc_map_addr'], string_dict['map_section'])
            return trace_msg
        else:
            return None

    def process_dict(self, string_dict):
        # wrong string, try next
        if 'msg_id' not in string_dict:
            return

        # process function entry - save in list until we find correcponding exit
        elif string_dict['msg_id'] == MSG_ENTRY:
            self.pending_item_list.append(string_dict)
            if self.trace_start == 0:
                self.trace_start = string_dict['time']

        # process function exit - find corresponding entry in pending list
        elif string_dict['msg_id'] == MSG_EXIT:
            for pending_item in self.pending_item_list:
                if string_dict['pid'] == pending_item['pid'] and \
                        string_dict['tid'] == pending_item['tid'] and \
                        string_dict['pc_map_addr'] == pending_item['pc_map_addr']:
                    time = string_dict['time'] - pending_item['time']
                    self.pending_item_list.remove(pending_item)
                    # add function execution time to total library time
                    lib_name = string_dict['map_section']
                    if lib_name in self.libs_dict:
                        self.libs_dict[lib_name] += time
                    else:
                        self.libs_dict[lib_name] = time

            if self.trace_time:
                if string_dict['time'] > (self.trace_start + self.trace_time):
                    self.stop_flag = True

    def print_trace(self):
        sorted_libs_list = sorted(self.libs_dict, key=self.libs_dict.get, reverse=True)
        for lib in sorted_libs_list:
            logging.debug(lib + " " + str(self.libs_dict[lib]))

class TraceMem(object):
    def __init__(self):
        self.bin_list = []
        self.libs_list = []
        self.alloc_dict = {}

    def parse_process_info_str(self, line):
        # discard start of the line with duplicate app binary information
        # all we need is in 'dep_libs' section
        _, line = line.split("'dep_libs':")
        line = line.translate(None, " {}'\n")
        line_list = line.split(",")
        for i, _ in enumerate(line_list):
            if "low_addr:" in line_list[i]:
                # discard unnecessary descriptions in the start of the line
                _, low_addr = line_list[i].split(':')
                _, high_addr = line_list[i+1].split(':')
                _, bin_path = line_list[i+2].split(':')

                binary_dict = {}
                binary_dict['low_addr'] = int(low_addr, 0)
                binary_dict['high_addr'] = int(high_addr, 0)
                binary_dict['binary_path'] = bin_path
                self.bin_list.append(binary_dict)

    def process_msg(self, msg_dict):
        if 'msg_id' not in msg_dict:
            return

        if msg_dict['msg_id'] not in processed_mem_msgs:
            return

        if msg_dict['msg_id'] == MSG_MEM_BIN:
            self.add_mem_bin(msg_dict)

        if msg_dict['msg_id'] == MSG_MEM_EVT:
            self.process_mem_event(msg_dict)

    def add_mem_bin(self, msg_dict):
        if 'binary_path' not in msg_dict:
            return
        binary_dict = {}
        binary_dict['low_addr'] = msg_dict['low_addr']
        binary_dict['high_addr'] = msg_dict['high_addr']
        binary_dict['binary_path'] = msg_dict['binary_path']
        for old_bin_dict in self.bin_list:
            if not cmp(old_bin_dict, binary_dict):
                print_err("Duplicate entries: ")
                print_err(binary_dict)
                return
        self.bin_list.append(binary_dict)

    def get_binary_by_addr(self, addr):
        binary_name = 'none'
        count = 0
        for binary_item in self.bin_list:
            if binary_item['low_addr'] <= addr <= binary_item['high_addr']:
                binary_name = binary_item['binary_path']
                count += 1
        if count > 1:
            print_err("Error: addr in two ranges: " + hex(addr) + " " + binary_name)
        if binary_name == 'none':
            print_err("Binary not found: %x" % addr)
        return binary_name

    def process_mem_event(self, msg_dict):
        if 'api_id_str' not in msg_dict:
            return

        for keyword in mem_alloc_funcs:
            if keyword in msg_dict['api_id_str']:
                self.process_mem_alloc(msg_dict)

        for keyword in mem_free_funcs:
            if keyword in msg_dict['api_id_str']:
                self.process_mem_free(msg_dict)

        for keyword in mem_realloc_funcs:
            if keyword in msg_dict['api_id_str']:
                self.process_mem_realloc(msg_dict)

    def process_mem_alloc(self, msg_dict):
        msg_bin_path = self.get_binary_by_addr(msg_dict['caller_pc_address'])

        # add event to allocation dict
        self.alloc_dict[msg_dict['addr']] = [msg_bin_path, msg_dict['size']]

        # add event to libraries list and count totals
        for lib_dict in self.libs_list:
            if lib_dict['binary_path'] == msg_bin_path:
                lib_dict['total_size'] += msg_dict['size']
                lib_dict['total_count'] += 1
                return

        # if lib is not in list yet
        lib_dict = {}
        lib_dict['binary_path'] = msg_bin_path
        lib_dict['total_size'] = msg_dict['size']
        lib_dict['total_count'] = 1
        lib_dict['free_size'] = 0
        lib_dict['free_count'] = 0
        self.libs_list.append(lib_dict)

    def process_mem_free(self, msg_dict):
        msg_bin_path = self.get_binary_by_addr(msg_dict['caller_pc_address'])

        try:
            alloc_data = self.alloc_dict.pop(msg_dict['addr'])
        except:
            print_err('Error: empty list on free ' + hex(msg_dict['addr']))
            return

        if alloc_data == None:
            print_err("Error: free request for address that wasn't allocated in trace:")
            print_err(msg_dict)
            return
        else:
            for lib_dict in self.libs_list:
                if lib_dict['binary_path'] == alloc_data[0]:
                    lib_dict['free_size'] += alloc_data[1]
                    lib_dict['free_count'] += 1
                    return

        # if lib is not in list yet - free before alloc? should be error
        print_err('Error: free before alloc, lib: ' + msg_bin_path)
        print_err(msg_dict)

    def process_mem_realloc(self, msg_dict):
        msg_bin_path = self.get_binary_by_addr(msg_dict['caller_pc_address'])

        old_addr = msg_dict['arg_0_val']
        new_addr = msg_dict['return_val']

        # check if it's reallocation of null pointer - it is a valid case
        if old_addr == 0 and msg_dict['errno'] == 0:
            # init with zero starting size
            alloc_data = [msg_bin_path, 0]
        else:
            try:
                alloc_data = self.alloc_dict.pop(old_addr)
            except:
                print_err('Error: empty list on realloc ' + hex(old_addr) + ' ' + hex(new_addr))
                return

        if alloc_data == None:
            print_err("Error: realloc request for address that wasn't allocated in trace:")
            print_err(msg_dict)
            return
        else:
            for lib_dict in self.libs_list:
                if lib_dict['binary_path'] == alloc_data[0]:
                    # count freed memory after realloc
                    lib_dict['free_size'] += alloc_data[1]
                    lib_dict['free_count'] += 1

                    # count newly allocated memory after realloc
                    if msg_dict['size'] > 0:
                        lib_dict['total_size'] += msg_dict['size']
                        lib_dict['total_count'] += 1
                    else:
                        print_err('Realloc with size = 0')

                    # add reallocated memory to allocation dict (addr and size can be changed)
                    self.alloc_dict[new_addr] = [msg_bin_path, msg_dict['size']]
                    return

            # if realloc lib not in list and old addr is 0, it is first reallocation
            # of null pointer, we should process as a first allocation
            if alloc_data[1] == 0 and old_addr == 0:
                # if lib is not in list yet
                lib_dict = {}
                lib_dict['binary_path'] = msg_bin_path
                lib_dict['total_size'] = msg_dict['size']
                lib_dict['total_count'] = 1
                lib_dict['free_size'] = 0
                lib_dict['free_count'] = 0
                self.libs_list.append(lib_dict)
                print_err('Added zero-addr realloc')
                return

        # if lib is not in list yet - realloc before alloc? should be error
        print_err('Error: realloc before alloc, lib: ' + msg_bin_path)
        print_err(msg_dict)

    def count_persistent_mem(self):
        for lib_dict in self.libs_list:
            lib_dict['pers_size'] = lib_dict['total_size'] - lib_dict['free_size']
            lib_dict['pers_count'] = lib_dict['total_count'] - lib_dict['free_count']
            if lib_dict['total_size'] - lib_dict['free_size'] < 0:
                lib_dict['pers_size'] = 0
            if lib_dict['total_count'] - lib_dict['free_count'] < 0:
                lib_dict['pers_count'] = 0

    def print_libs_list(self):
        for item in self.libs_list:
            logging.debug(item)

previos_time = 0
class TraceTree(object):
    def __init__(self, trace_time = 0):
        self.root_node = TraceNode()
        self.tid_root_nodes = {}
        self.open_nodes = [] # list of open nodes tuples: (TID, time, node)
        self.current_nodes = {} # current nodes for each thread: dict { TID : node }
        self.trace_time = trace_time
        self.trace_start = 0
        self.trace_finish = 0
        self.stop_flag = False
        self.lib_call_count = {}
        self.entry = 0
        self.exit = 0
        self.context_entry = 0
        self.context_exit = 0

    def process_msg(self, msg_dict):
        # not message string, try next

        global previos_time
        try:
            if msg_dict['msg_id'] == 0x00009 or msg_dict['msg_id'] == 0x00008 or msg_dict['msg_id'] == 0x00010 or msg_dict['msg_id'] == 0x00011:
                if previos_time > msg_dict['time']:
                    logging.debug("EVENTS is not sorted")
                    logging.debug(previos_time)
                    logging.debug(msg_dict['time'])

                previos_time = msg_dict['time']
        except:
            pass

        if 'msg_id' not in msg_dict:
            return

        # message type we don't process, try next
        if msg_dict['msg_id'] not in processed_msgs:
            return

        # ignore strange trace messages with same map addresses

        if msg_dict['msg_id'] == MSG_ENTRY or msg_dict['msg_id'] == MSG_EXIT:
            if msg_dict['map_section'] == '?' or msg_dict['pc_map_addr'] == 0xffffffff:
                return

        if msg_dict['msg_id'] == MSG_ENTRY:
            self.open_node(msg_dict)
            self.entry += 1

        elif msg_dict['msg_id'] == MSG_EXIT:
            # check open nodes, close one corresponding to message
            self.close_node(msg_dict)
            self.exit += 1

        elif msg_dict['msg_id'] == MSG_CONTEXT_ENTRY:
            self.extend_to_function(msg_dict)
            self.open_node(msg_dict)
            self.context_entry += 1

        elif msg_dict['msg_id'] == MSG_CONTEXT_EXIT:
            self.extend_to_function(msg_dict)
            self.close_node(msg_dict)
            self.context_exit += 1
        else:
            logging.debug("msg_dict['msg_id']" + str(msg_dict['msg_id']))

    def extend_to_function(self, msg_dict):
        msg_dict['map_section'] = "context_switch"
        msg_dict['pc_map_addr'] = -1

    # check nodes on level, open old one or create new node
    def open_node(self, msg_dict):
        # if we need to cut trace on some time point
        if self.trace_time:
            # if we have no start time mark yet, set start and finish
            if self.trace_start == 0:
                self.trace_start = msg_dict['time']
                self.trace_finish = self.trace_start + (self.trace_time * 1000000)

            # if current entry is beyond finish mark, discard it (and set stop flag?)
            if msg_dict['time'] > self.trace_finish:
                return

        if msg_dict['map_section'] in self.lib_call_count:
            self.lib_call_count[msg_dict['map_section']] += 1
        else:
            self.lib_call_count[msg_dict['map_section']] = 1

        # if we have current node for TID, work with it
        if msg_dict['tid'] not in self.current_nodes:
            if msg_dict['tid'] == msg_dict['pid']:
                logging.debug("Found main thread with pid " + str(msg_dict['pid']))
                current_node = self.root_node
            elif msg_dict['tid'] not in self.tid_root_nodes:
                logging.debug("Found new thread with tid " + str(msg_dict['tid']))
                current_node = TraceNode()
                self.tid_root_nodes[msg_dict['tid']] = current_node
            else:
                current_node = self.tid_root_nodes[msg_dict['tid']]
        else:
            current_node = self.current_nodes[msg_dict['tid']]

        # check for map_addr of child nodes, reopen existing or create new
        node_to_open = current_node.search_children(msg_dict['pc_map_addr'],
                msg_dict['map_section'])
        # if not found - create new node and append to children
        if not node_to_open:
            node_to_open = TraceNode()
            node_to_open.fill(msg_dict['pc_map_addr'], msg_dict['map_section'],
                    current_node)
            current_node.children.append(node_to_open)

        # add node to open_nodes
        self.open_nodes.append((msg_dict['tid'], msg_dict['time'], node_to_open))

        # update current_node for TID to newly open node
        self.current_nodes[msg_dict['tid']] = node_to_open

    # find corresponding open node, count time, close node
    def close_node(self, msg_dict):
        # partial trace file, exit event before any entries
        if not self.open_nodes:
            print_err("Error: request to exit from function with no open entry")
            print_err(msg_dict)
            return
        if msg_dict['tid'] not in self.current_nodes:
            # partial trace file, no entry for this exit, no need to process
            print_err("Error: request to exit from function with no open entry for TID")
            print_err(msg_dict)
            return
        else:
            current_node = self.current_nodes[msg_dict['tid']]

        if current_node.lib_name != msg_dict['map_section'] or current_node.map_addr != msg_dict['pc_map_addr']:
            logging.debug("Trying to close node:")
            logging.debug(current_node)
            logging.debug("With event:")
            logging.debug(msg_dict)
#            assert(0)

        for open_tuple in self.open_nodes:
            if open_tuple[0] == msg_dict['tid'] and open_tuple[2] == current_node:
                break

        # count and update time, calls count
        if self.trace_time != 0 and msg_dict['time'] > self.trace_finish:
            funct_time = self.trace_finish - open_tuple[1]
        else:
            funct_time = msg_dict['time'] - open_tuple[1]
        current_node.tot_time += funct_time
        current_node.tot_calls += 1

        # remove tuple from list of open nodes
        self.open_nodes.remove(open_tuple)

        # reset current_node for TID to node's parent if it is not None
        if current_node.parent:
            self.current_nodes[msg_dict['tid']] = current_node.parent
        else:
            # workaround, reset current node for TID to root node and print error
            self.current_nodes[msg_dict['tid']] = self.root_node
            print_err("Error: try to exit from function to level upper than root function")
            print_err(msg_dict)

    def count_self_times_for_tree(self):
        self.count_self_times_recursively(self.root_node)

    # count function's self run time by substructing child's time from parent's time
    def count_self_times_recursively(self, trace_node):
        children_time = 0
        if trace_node.is_leaf():
            trace_node.self_time = trace_node.tot_time
        else:
            for child in trace_node.children:
                self.count_self_times_recursively(child)
                children_time += child.tot_time
                if trace_node.tot_time > 0:
                    trace_node.self_time = trace_node.tot_time - children_time
                    if trace_node.self_time < 0:
                        logging.debug(trace_node)
                        logging.debug("child = " + str(child))

    def print_tree_by_function(self):
        self.print_node_children_recursively(self.root_node, 0)

    # print node's children on their level
    def print_node_children_recursively(self, trace_node, level):
        logging.debug("-" * level + trace_node.get_string())
        if not trace_node.is_leaf():
            for child in trace_node.children:
                self.print_node_children_recursively(child, level + 1)

    def fix_open_nodes(self):
        if self.open_nodes:
            for trace_node in self.open_nodes:
                print_err("Error: node is not closed")
                print_err(trace_node[2].get_string())
                if trace_node[2].tot_time != 0:
                    trace_node[2].tot_time = 0

    def sort_tree_by_tot_time(self):
        self.sort_nodes_recursively(self.root_node)

    def sort_nodes_recursively(self, trace_node):
        if not trace_node.is_leaf():
            trace_node.children.sort(key=lambda x: x.tot_time, reverse=True)
            for child in trace_node.children:
                self.sort_nodes_recursively(child)

    def make_and_print_xml_tree(self):
        self.xml_tree_root = ET.Element("root")
        self.add_xml_tree_elements_recursively(self.root_node, self.xml_tree_root, 1)
        self.xml_tree = ET.ElementTree(self.xml_tree_root)
#        self.xml_tree.write("trace_tree.xml")

    def add_xml_tree_elements_recursively(self, trace_node, tree_element, level):
        if not trace_node.is_leaf():
            for child_node in trace_node.children:
                child_element = ET.SubElement(tree_element, "l" + str(level),
                        addr=hex(child_node.map_addr), lib=child_node.lib_name,
                        tot_time=str(child_node.tot_time), self_time=str(child_node.self_time),
                        calls=str(child_node.tot_calls))
                self.add_xml_tree_elements_recursively(child_node, child_element, level + 1)

    def make_libs_dictionary(self):
        self.libs_dict = {}
        self.count_libs_in_tree_recursively(self.root_node)

    def count_libs_in_tree_recursively(self, trace_node):
        for child in trace_node.children:
            if child.lib_name in self.libs_dict:
                self.libs_dict[child.lib_name] += child.self_time
            else:
                self.libs_dict[child.lib_name] = child.self_time
            self.count_libs_in_tree_recursively(child)

    def print_libs_dictionary(self):
        if self.libs_dict:
            sorted_libs_list = sorted(self.libs_dict, key=self.libs_dict.get, reverse=True)
            for lib in sorted_libs_list:
                logging.debug(lib + " " + str(self.libs_dict[lib]))

        logging.debug("Func entry = " + str(self.entry))
        logging.debug("Func exit = " + str(self.exit))
        logging.debug("Context switch entry = " + str(self.context_entry))
        logging.debug("Context switch exit = " + str(self.context_exit))

class TraceNode(object):
    def __init__(self):
        self.map_addr = 0
        self.lib_name = None
        self.tot_calls = 0
        self.tot_time = 0
        self.self_time = 0
        self.parent = None
        self.children = []

    def __repr__(self):
        result = "map_addr = %s lib_name = %s tot_calls = %s tot_time = %s self_time = %s" \
                % (self.map_addr, self.lib_name, self.tot_calls,
                        self.tot_time, self.self_time)
        return result

    def fill(self, map_addr, lib_name,
                parent):
        self.map_addr = map_addr
        self.lib_name = lib_name
        self.parent = parent

    def search_children(self, map_addr, lib_name):
        if self.children == []:
            return None

        for child in self.children:
            if child.map_addr == map_addr and child.lib_name == lib_name:
                return child

        # nothing is found
        return None

    def is_root(self):
        if not self.parent:
            return True
        else:
            return False

    def is_leaf(self):
        if not self.children:
            return True
        else:
            return False

    def get_string(self):
        if self.is_root():
            return "root"
        else:
            return "addr: " + hex(self.map_addr) + " lib: " + self.lib_name +\
                    " tot_time: " + str(self.tot_time) + " self_time: " + str(self.self_time) +\
                    " calls: " + str(self.tot_calls)

    def get_xml_attrs_string(self):
        return 'addr="' + hex(self.map_addr) + '" lib="' + self.lib_name +\
                '" tot_time="' + str(self.tot_time) + '" self_time="' + str(self.self_time) +\
                '" calls="' + str(self.tot_calls) + '"'

# UNUSED
class TraceMsg(object):
    def __init__(self):
        self.msg_id = 0
        self.time = 0
        self.tid = 0
        self.map_addr = 0
        self.lib_name = None

    def fill(self, msg_id, time, tid, map_addr, lib_name):
        self.msg_id = msg_id
        self.time = time
        self.tid = tid
        self.map_addr = map_addr
        self.lib_name = lib_name

def main():
    swap_parser = SwapParser()
    set_args(swap_parser)
    if swap_parser.trace_type == TRACE_FUNCTIONS:
        swap_parser.parse_trace_file_to_tree()
        swap_parser.trace_tree.count_self_times_for_tree()
        swap_parser.trace_tree.sort_tree_by_tot_time()
        swap_parser.trace_tree.make_and_print_xml_tree()
        swap_parser.trace_tree.make_libs_dictionary()
        swap_parser.trace_tree.print_libs_dictionary()
    elif swap_parser.trace_type == TRACE_MEMORY:
        swap_parser.parse_trace_file_mem()
        swap_parser.trace_mem.count_persistent_mem()
        swap_parser.trace_mem.print_libs_list()

def set_args(swap_parser):
    arg_parser = argparse.ArgumentParser(description='Parse swap trace file')
    arg_parser.add_argument('-t', type=int, dest='trace_time',
            help = 'When to stop parsing, in milliseconds')
    arg_parser.add_argument('-f', dest='trace_file',
            help = 'File to trace')
    arg_parser.add_argument('-v', dest='verbose', action='store_true',
            help='Print errors')
    arg_parser.add_argument('-l', dest='libraries', action='store_true',
            help='Print summary by libraries')
    arg_parser.add_argument('-m', dest='mem_trace', action='store_true',
            help='Parse memory events trace')
    args = arg_parser.parse_args()
    if args.trace_time:
        swap_parser.trace_time = args.trace_time
    if args.trace_file:
        swap_parser.trace_file = args.trace_file
    if args.verbose:
        global print_errors
        print_errors = True
    if args.libraries:
        global print_libraries
        print_libraries = True
    if args.mem_trace:
        swap_parser.trace_type = TRACE_MEMORY

if __name__=='__main__':
    main()

