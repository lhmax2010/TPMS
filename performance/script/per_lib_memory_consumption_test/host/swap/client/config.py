#!/usr/bin/python

import logging
import sys
import os
import subprocess
import ConfigParser

lib_path = ''
bin_path = ''
all = {}
def Echo(args):
    logging.critical(args)



class Config:
    file_name = None
    all = {}
    lib_func = {}
    bin_func = {}
    lib_probes = {}
    bin_probes = {}
    def GenDummyConf(self, replay_on):
        features =(0x000000000000FFFF)
        system_trace_period = 10
        data_message_period = 50
        us_inst1 = ("calculator", [(0x8000, "ps"), (0x8010, "psd")])
        libs_inst1 = [("libc1.so", [(0x16000, "ps"), (0x16010, "psc")]),
                     ("libpthread1.so", [(0x18000, "ps")])]


        app_inst1 = [0x0001,"calc app id1",us_inst1, libs_inst1]
        app_inst_list = [app_inst1]#,app_inst2]
        dummy={
                'app_info' : (3, "com.samsung.calculator", "/usr/apps/com.samsung.calculator/bin/hz"),
                'conf' : (features, system_trace_period, data_message_period),
                'app_inst_list' : app_inst_list,
                'replay' : None
                }
        if replay_on != 0:
            dummy['replay'] = events
        return dummy

    def lib_list_import(self, name):
        mod = __import__(name, globals(), locals(), ['lib_inst_list'], -1)
        reload(mod)
        if hasattr(mod,'lib_inst_list'):
            logging.debug("mod.lib_inst_list:")
            logging.debug(mod.lib_inst_list)
            return mod.lib_inst_list
        else:
            logging.debug('[Error] lib_inst_list not found in "%s.py"' % name)
            return None

    def app_list_import(self, name):
        mod = __import__(name, globals(), locals(), ['app_inst_list'], -1)
        reload(mod)
        if hasattr(mod,'app_inst_list'):
            logging.debug("mod.app_inst_list:")
            logging.debug(mod.app_inst_list)
            return mod.app_inst_list
        else:
            logging.debug('[Error] app_inst_list not found in "%s.py"' % name)
            return None

    def replay_import(self, name):
        if not os.path.isfile(name.replace(".","/")):
            logging.debug('[Error] module not found "%s"' % name)
        mod = __import__(name, globals(), locals(), ['replay'], -1)
        reload(mod)
        if hasattr(mod,'replay'):
            return mod.replay
        else:
            logging.debug('[Error] replay not found in "%s.py"' % name)
            return None

    def self_import(self, name, attr):
        filename = './' + name.replace(".","/")+ '.py'
        if not os.path.isfile(filename):
            logging.debug('[Error] module not found "%s" (%s)' % (name, filename))
            return None
        mod = __import__(name, globals(), locals(), [attr], -1)
        reload(mod)
        if hasattr(mod,attr):
            return getattr(mod,attr)
        else:
            logging.debug('[Error] obj <%s> not found in "%s"' % (attr, filename))
            return None

    def LoadConfig(self, target_conf_name = None, test_conf_path = None):
        self.config = None
        self.test_conf_path = test_conf_path

        if not test_conf_path is None:
            self.config = {}

            # Target device parameters
            curr_path = os.getcwd()
            main_test_conf_path = os.path.abspath(os.path.dirname(__file__) + "/../")
            os.chdir(main_test_conf_path)
            self.config =  self.self_import(target_conf_name, 'target_settings');
            if self.config is None:
                logging.debug('[ERR] "target_settings" not found in <%s>' % target_conf_name)
                return 0

            check_list = [
                    'target_is_virtual',
                    'target_ip',
                    'connection_type',
            ]
            for elm in check_list:
                if not elm in self.config:
                    logging.debug("[ERR] '%s' is None in <%s> config" % (elm, target_conf_name))
                    return 0

            if not 'da_manager_exec_cmd' in self.config:
                self.config['da_manager_exec_cmd'] = 'da_manager'

            os.chdir(curr_path)
            profile_settings = self.self_import(test_conf_path + '.conf', 'profile_settings')
            if profile_settings is None:
                logging.debug('[Err] profile_settings not found in <%s>' % test_conf_path)
                return 0

            # Testcase parameters
            features = self.self_import(test_conf_path + '.conf', 'features');
            if features is None:
                logging.debug("Features is None")
                return 0
            list = ['willExecute', 'didExecute', 'startInspectorServer', 'enable_probe_type_support']
            for elm in list:
                if not elm in profile_settings:
                    profile_settings[elm] = None
            self.config['addr'] = (profile_settings['willExecute'],
                                   profile_settings['didExecute'],
                                   profile_settings['startInspectorServer'])

            self.config.update(profile_settings)
            if self.config['enable_probe_type_support'] is None:
                self.config['enable_probe_type_support'] = 0

            self.config['conf'] = {'features': features,
                                   'system_trace_period': self.config['system_trace_period'],
                                   'data_message_period': self.config['data_message_period']}

            logging.debug("Importing from file: " + test_conf_path + '.user_space_inst_list' )
            self.config['app_inst_list'] = self.self_import(test_conf_path + '.user_space_inst_list', 'app_inst_list')
            self.config['lib_inst_list'] = self.self_import(test_conf_path + '.user_space_inst_list', 'lib_inst_list')
            self.config['replay'] = self.self_import(test_conf_path + '.replay', 'replay')

            if 'install_app_path' in self.config:
                for app in self.config['app_inst_list']:
                    path = app['app_path']
                    if not "%s" in path:
                        continue
                    path = path % self.config['install_app_path']
                    app['app_path'] = path

            self.config['app_inst_list']
            logging.debug('<CONFIG>')
            for elm in self.config:
                if elm != 'replay' and elm != 'lib_inst_list':
                    logging.debug('%s: %s' % (elm, self.config[elm]))
            return 1
        return 0

    def __init__(self):
        return

    def __del__(self):
        return

    def GetAppInst(self):
        Echo('GetAppInst start')
        us_inst = []
        lib_inst = []
        app_inst_list = [];

        for app in self.bin_probes:
            Echo(app)
            short_name = app.split('/')[-1]
            us_inst.append( [short_name,[]] );
            for addr in self.bin_probes[app]:
                addr = int(addr,16)
                us_inst[-1][1].append((addr,"ps"))

        for app in self.lib_probes:
            Echo(app)
            lib_inst.append([]);
            for lib in self.lib_probes[app]:
                lib_inst[-1].append((lib,[]))
                Echo(lib)
                for addr in self.lib_probes[app][lib]:
                    addr = int(addr, 16)
                    lib_inst[-1][-1][1].append((addr,"ps"))
                    Echo(addr)
        #app_short_name =
        #us_inst = ()
        Echo(us_inst[0])
        Echo(lib_inst[0])

        for i in range(0,len(us_inst)):
            app_inst_list.append([0x0001, "some id", us_inst[i], lib_inst[i]])
        Echo(app_inst_list)
        return app_inst_list

    def GetConfig(self, replays_on):
        if self.test_conf_path is None:
            return self.GenDummyConf(replays_on)
        else:
            return self.config

#Config(sys.argv[1])
