#!/usr/bin/python
import logging

def exit_fail(fail_msg):
    logging.critical("FAIL: %s" % fail_msg)

def exit_env(env_msg):
    logging.critical("ENV: %s" % env_msg)

def warn(warn_msg):
    logging.debug("WARNING: %s" % warn_msg)
