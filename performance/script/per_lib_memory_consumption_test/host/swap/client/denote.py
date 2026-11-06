#!/usr/bin/python

import logging
import os
import re

from client_lib import exec_cmd

class Denote():
    def __init__(self):
        # Check "objdump" utility
        if exec_cmd("objdump -v | grep \"GNU objdump\" > /dev/null")[0] != 0:
            logging.debug("[ERROR] can not find \"objdump\" utility on your host")
            exit(1)

        # Structure of lib_cache:
        # { <full_lib_name> : <lib_name> }
        #
        # for example:
        # { "libpthread.so" : "/lib/libpthread.so.0" ,
        #   "libc.so"       : "/lib/libc.so.6" }
        self.lib_cache = dict()

        # Structure of func_cache:
        # { <full_lib_name> : { 'load_addr' : <load_addr>,
        #                       'func_addr_dict' : { <func_name> : <func_addr> } } }
        #
        # for example:
        # { "/lib/libpthread.so.0" : { 'load_addr' : 123000,
        #                              'func_addr_dict' : { "pthread_create" : 124000,
        #                                                   "pthread_join"   : 125000 } } ,
        #   "/lib/libc.so.6"       : { 'load_addr' : 223000,
        #                              'func_addr_dict' : { "malloc" : 224000 } } }
        self.func_cache = dict()

        return

    # ------------------------
    # *** Work with caches ***
    # ------------------------
    def get_full_lib_name(self, cl, lib):
        # Places on target where libraries should be checked
        search_paths="/lib /usr/lib"

        # Always get first corresponding library
        out = cl.deviceIntr.shell("find %s | grep %s | head -n1" % (search_paths, lib))
        if out[0] == -1:
            logging.debug("[ERROR] can not run \"find\" on target")
            return None
        res = out[1].strip()
        if not res:
            out = cl.deviceIntr.shell("find / | grep %s | head -n1" % (lib))
            res = out[1].strip()
            if not res:
                logging.debug("[ERROR] can not find %s on target" % lib)
                return None
        return res

    def pull_lib(self, cl, full_lib):
        local_lib = re.sub(r'^.*/', "/tmp/", full_lib)
        if cl.deviceIntr.pull(full_lib, local_lib)[0] == -1:
            logging.debug("[ERROR] can not get \"%s\" file from target" % full_lib)
            return None
        return local_lib

    def remove_lib(self, local_lib):
        os.remove(local_lib)

    def get_lib_addrs(self, local_lib):
        lib_addr_dict = dict()
        func_addr_dict = dict()

        # Write library load address in lib_addr_dict['load_addr']
        load_addr = exec_cmd("objdump -x %s | grep -m1 \"LOAD.*off\" | awk '{print $5}' | sed -e \"s/^0x//\"" % local_lib)[1].strip()
        if re.match(r'^[0-9a-f]+$', load_addr) is None:
            load_addr = 0
        else:
            load_addr = int(load_addr, 16)
        lib_addr_dict['load_addr'] = load_addr


        # Fill lib_addr_dict['func_addr_dict'] with function addresses
        func_addr_text = exec_cmd("objdump -t -T %s | grep \"F[[:blank:]*]\.text\" | awk '{print $NF,$1}'" % local_lib)[1].strip()
        for func_addr_line in func_addr_text.splitlines():
            func_name = re.sub(r' .*$', "", func_addr_line)
            # Always get address of first corresponding function
            if not func_name in func_addr_dict:
                func_addr = re.sub(r'^.* ', "", func_addr_line)
                if re.match(r'^[0-9a-f]+$', func_addr) is None:
                    logging.debug("[ERROR] incorrect \"%s\" function address (%s) in %s library" % (func_name, func_addr, local_lib))
                    return None
                func_addr = int(func_addr, 16)
                func_addr_dict[func_name] = func_addr
        lib_addr_dict['func_addr_dict'] = func_addr_dict

        return lib_addr_dict

    def fill_lib_cache(self, cl):
        # For executables:
        for app_inst in cl.conf['app_inst_list']:
            executable = app_inst['app_path']
            if not executable in self.lib_cache:
                # Fill lib_cache
                self.lib_cache[executable] = executable

        # For libraries:
        for lib_inst in cl.conf['lib_inst_list']:
            for lib in lib_inst:
                if not lib in self.lib_cache:
                    if re.match(r'^/', lib) is None:
                        # If library name is given - find full library name
                        full_lib = self.get_full_lib_name(cl, lib)
                        if full_lib is None:
                            return None
                    else:
                        # If full library name is already given - do nothing
                        full_lib = lib

                    # Fill lib_cache
                    self.lib_cache[lib] = full_lib

        return self.lib_cache

    def fill_func_cache(self, cl):
        for full_lib in self.lib_cache.itervalues():
            if not full_lib in self.func_cache:
                # Pull temporary library from target
                local_lib = re.sub(r'^.*/', "/tmp/", full_lib)
                if not os.path.exists(local_lib):
                    local_lib = self.pull_lib(cl, full_lib)
                if local_lib is None:
                    return None

                # Get function address dictionary from library
                lib_addrs = self.get_lib_addrs(local_lib)
                if lib_addrs is None:
                    return None
                self.func_cache[full_lib] = lib_addrs

                # Remove temporary library from host
                self.remove_lib(local_lib)

        return self.func_cache

    # -----------------------------------------------------
    # *** Names & addresses resolution lambda-functions ***
    # -----------------------------------------------------
    def resolve_probe(self, lib_name, probe):
        try:
            func = probe[0]
            if type(func) is str:
                # Unlock probe
                probe = list(probe)

                # Find function address by its name in cache
                load_addr = self.func_cache[lib_name]['load_addr']
                func_addr = self.func_cache[lib_name]['func_addr_dict'][func]
                probe[0] = func_addr - load_addr

                # Lock probe back
                probe = tuple(probe)
            return probe
        except:
            import logging
            logging.critical("Probe %s not found!" % (func))
            return None

    def resolve_life_cycle_probe(self, lib_name, func):
        try:
            if type(func) is str:
                # Find function address by its name in cache
                func = self.func_cache[lib_name]['func_addr_dict'][func]
            return func
        except:
            import logging
            logging.critical("Probe %s not found!" % (func))
            return None

    def resolve_app_inst(self, app_inst):
        app = app_inst['app_path']
        app_inst['app_probes'] = filter(lambda x: x != None, map(lambda probe: self.resolve_probe(app, probe), app_inst['app_probes']))

        app_inst['life_cycle_probes'] = filter(lambda x: x != None,  map(lambda probe: self.resolve_life_cycle_probe(app, probe), app_inst['life_cycle_probes']))
        return app_inst

    def resolve_lib_inst_item(self, lib_inst_item):
        lib_name = lib_inst_item[0]
        if re.match(r'^/', lib_name) is None:
            # Update library name to full one
            lib_name = self.lib_cache[lib_name]
        lib_probe_list = map(lambda probe: self.resolve_probe(lib_name, probe), lib_inst_item[1])
        return (lib_name, lib_probe_list)

    def resolve_lib_inst(self, lib_inst):
        return dict(map(lambda item: self.resolve_lib_inst_item(item), lib_inst.iteritems()))

    # ------------------
    # *** Denote API ***
    # ------------------
    def resolve_config(self, cl):
        # Make caches for libraries and functions
        if self.fill_lib_cache(cl) is None:
            return None
        if self.fill_func_cache(cl) is None:
            return None

        # 1. Resolve function addresses per each executable in cl.conf['app_inst_list']
        cl.conf['app_inst_list'] = map(lambda x: self.resolve_app_inst(x), cl.conf['app_inst_list'])

        # 2. Resolve library names in and function addresses per each library in cl.conf['lib_inst_list']
        cl.conf['lib_inst_list'] = map(lambda x: self.resolve_lib_inst(x), cl.conf['lib_inst_list'])

        return cl.conf
