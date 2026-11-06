"""Real sdb wire format passed through the production checked transport.

No board connection. The mock replaces only Popen/UUID, never output parsing.
"""
import ast
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch

UUID = '0c21108125ea4d75a3b4836b9f837642'
MARKER = 'TPMS_RC_' + UUID
ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT/'standalone/tpms_util.py').read_text())
method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'executeCmd_result')
namespace = dict(subprocess=subprocess, os=os, time=time, signal=signal, re=re)
exec(compile(ast.Module(body=[method], type_ignores=[]), 'checked-transport-fixture', 'exec'), namespace)


def sdb_wire_output(payload, rc=0):
    """sdb PTY converts LF to CRLF, including the printf separator/trailer."""
    return (payload+'\n'+MARKER+':'+str(rc)+'\n').replace('\n', '\r\n')


def sdb_result(payload='', rc=0, stderr='', raw_stdout=None, transport_rc=0):
    raw = sdb_wire_output(payload, rc) if raw_stdout is None else raw_stdout
    process = SimpleNamespace(returncode=transport_rc,
                              communicate=lambda timeout: (raw.encode(), stderr.encode()))
    device = SimpleNamespace(_CMD='offline-fake-sdb', _dev_serial='fixture')
    with patch('subprocess.Popen', return_value=process), patch('uuid.uuid4', return_value=SimpleNamespace(hex=UUID)):
        return namespace['executeCmd_result'](device, 'fixture command', 1)
