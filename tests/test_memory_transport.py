"""Regression coverage for actual sdb framing; no device is contacted."""
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sdb_output_fixture import MARKER, UUID, namespace, sdb_result
from test_memory_runner import FakeOwner, MemoryRigorRunner

SMOKE_ROOT = '0\r\n\r\nTPMS_RC_0c21108125ea4d75a3b4836b9f837642:0\r\n'


class CheckedOutputTests(unittest.TestCase):
    def test_original_smoke_output(self):
        result=sdb_result(raw_stdout=SMOKE_ROOT)
        self.assertEqual(result['stdout'],'0\n')
        self.assertEqual(result['raw_stdout'],SMOKE_ROOT)
        self.assertEqual(result['returncode'],0)

    def test_preserves_command_newlines(self):
        for payload in ('', 'value', 'value\n', 'value\n\n', 'a\nb\n'):
            with self.subTest(payload=payload):
                self.assertEqual(sdb_result(payload)['stdout'],payload)

    def test_missing_marker_normalizes_only(self):
        result=sdb_result(raw_stdout='5001\r\n\r\n')
        self.assertIsNone(result['returncode'])
        self.assertEqual(result['stdout'],'5001\n\n')
        self.assertEqual(result['raw_stdout'],'5001\r\n\r\n')

    def test_marker_like_command_data_preserved(self):
        payload='TPMS_RC_other:0\n'+MARKER+':4\nnext\n'
        self.assertEqual(sdb_result(payload)['stdout'],payload)

    def test_nonzero_transport_remains_unknown(self):
        result=sdb_result('value\n',transport_rc=1)
        self.assertIsNone(result['returncode'])
        self.assertEqual(result['stdout'],'value\n')

    def test_timeout_still_unknown_and_preserves_raw(self):
        process=SimpleNamespace(returncode=0,pid=123)
        device=SimpleNamespace(_CMD='fake',_dev_serial='fixture')
        with patch('subprocess.Popen',return_value=process), patch('uuid.uuid4',return_value=SimpleNamespace(hex=UUID)), patch('os.killpg') as kill:
            process.communicate=unittest.mock.Mock(side_effect=[subprocess.TimeoutExpired('fake',1),(SMOKE_ROOT.encode(),b'')])
            result=namespace['executeCmd_result'](device,'id -u',1)
        kill.assert_called_once_with(123,signal.SIGTERM)
        self.assertTrue(result['timed_out']);self.assertIsNone(result['returncode'])
        self.assertEqual(result['stdout'],'0\n');self.assertEqual(result['raw_stdout'],SMOKE_ROOT)


class PrepareRealOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.owner=FakeOwner(Path(self.tmp.name));self.runner=MemoryRigorRunner(self.owner)
        self.uid=SMOKE_ROOT;self.bad_hash=False;self.pushes=[]
        self.owner.executeCmd_result=self.execute
        self.owner.transfer_result=self.transfer

    def execute(self,cmd,timeout):
        if cmd=='id -u':return sdb_result(raw_stdout=self.uid)
        if cmd.startswith('sha256sum '):
            digest='0'*64 if self.bad_hash else hashlib.sha256(self.runner.script.read_bytes()).hexdigest()
            return sdb_result(digest+'  '+self.runner.remote_script+'\n')
        return sdb_result()

    def transfer(self,*args):
        self.pushes.append(args)
        return dict(returncode=0,stdout='',stderr='')

    def test_smoke_root_passes_strict_check_and_logs_both(self):
        self.runner.prepare()
        result=json.loads((self.runner.root/'commands/root_check.json').read_text())
        self.assertEqual(result['stdout'],'0\n');self.assertEqual(result['raw_stdout'],SMOKE_ROOT)
        self.assertEqual(len(self.pushes),1)

    def test_uid_5001_rejected(self):
        self.uid=SMOKE_ROOT.replace('0\r\n','5001\r\n',1)
        with self.assertRaisesRegex(RuntimeError,'requires root'):self.runner.prepare()
        self.assertEqual(self.pushes,[])

    def test_uid_containing_zero_rejected(self):
        self.uid=SMOKE_ROOT.replace('0\r\n','5000\r\n',1)
        with self.assertRaisesRegex(RuntimeError,'requires root'):self.runner.prepare()

    def test_sha256_real_sdb_format(self):
        self.runner.prepare()
        result=json.loads((self.runner.root/'commands/payload_check.json').read_text())
        digest=hashlib.sha256(self.runner.script.read_bytes()).hexdigest()
        self.assertEqual(result['stdout'],digest+'  '+self.runner.remote_script+'\n')
        self.assertIn('\r\n\r\nTPMS_RC_',result['raw_stdout'])

    def test_sha256_mismatch_real_sdb_format_rejected(self):
        self.bad_hash=True
        with self.assertRaisesRegex(RuntimeError,'hash mismatch'):self.runner.prepare()
