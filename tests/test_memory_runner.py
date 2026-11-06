import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone'));sys.path.insert(0,str(ROOT/'db'))
from memory_rigor import config,run_quality,save_run,read_item
from memory_rigor_runner import MemoryRigorRunner
from memory_fixture import capture,item,run


class FakeOwner:
    def __init__(self,path,options=None):
        self.host_result_path=str(path);self.report_file=str(path/'report.txt')
        self.script_path=str(ROOT/'performance/script');self.target_out_path='/opt/usr/tpms/result';self.target_exe_path='/opt/usr/tpms/bin'
        self._snapshot_id='test-image';self.profile_name='10.0-tv-kantsu2e'
        self.memory_rigor=config(dict(enabled=True,boots=3,samples=5,**(options or {})))
        self._device=self;self.boot=0;self.reboot_ok=True
    def reboot_device(self):self.boot+=1;return self.reboot_ok
    def install_package_from_repo(self,pkg,allow_latest_fallback=True):
        assert pkg=='memps' and allow_latest_fallback
        self._memory_tool_url='fixture://memps.rpm';return True


class FakeRunner(MemoryRigorRunner):
    fail_sample=None
    def prepare(self):pass
    def cleanup(self,remote=None):
        result={'verified':True,'path':self.remote_root}
        if self.run is not None:self.run['cleanup']=result
        return result
    def gate(self,boot_index,gate_id=None):
        return dict(boot_index=boot_index,boot_id='boot'+str(self.owner.boot),status='steady',reason='steady_criteria_met',uptime=600,sequence=[])
    def capture(self,mode,sid):
        self.calls.append((mode,sid));d=self.root/sid;d.mkdir(exist_ok=True)
        capture(d,'boot'+str(self.owner.boot),sid)
        if mode=='snapshot':
            if self.fail_sample and self.fail_sample in sid:item(d,'memps.txt','')
            # Use archived valid memps to exercise original legacy column logic.
            if not (self.fail_sample and self.fail_sample in sid):item(d,'memps.txt',(ROOT/'tests/fixtures/memory_rigor/gcc_baseline/memps.txt').read_text())
        elif mode=='probe':item(d,'uptime','10000 20000')
        elif mode=='tools':
            item(d,'nevra','memps-0:0.2.0-0.armv7l');item(d,'sha256','a'*64+' /usr/bin/memps');item(d,'os-release','BUILD_ID=test-image')
        elif mode=='ion':item(d,'ion_write','');item(d,'ion_settle','')
        return d


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.owner=FakeOwner(self.path)
        self.runner=FakeRunner(self.owner);self.runner.calls=[]
    def tearDown(self):self.tmp.cleanup()
    def test_three_boots_five_samples(self):
        self.assertTrue(self.runner.collect());self.assertEqual(self.owner.boot,3)
        r=json.loads((self.path/'memory_rigor.json').read_text());self.assertEqual(len(r['samples']),15)
        self.assertTrue(run_quality(r)['valid']);self.assertEqual(len(r['tools']),3)
    def test_invalid_propagates_false_and_retained(self):
        self.runner.fail_sample='b2-s3-base';self.assertTrue(self.runner.collect())
        self.assertEqual(sum(not s['valid'] for s in self.runner.run['samples']),1)
        self.assertEqual(len(self.runner.run['samples']),15)
    def test_legacy_first_sample_only_and_reused_once(self):
        self.runner.collect()
        for k in ('memory_usage_test','process_memory_usage_test','memory_info_test'):
            self.assertTrue(self.runner.export_legacy(k))
        text=Path(self.owner.report_file).read_bytes()
        self.assertTrue(self.runner.export_legacy('memory_usage_test'))
        self.assertEqual(text,Path(self.owner.report_file).read_bytes())
        self.assertEqual(text.count(b"'name': 'IdleMemoryUsage'"),1)
    def test_invalid_first_never_substituted(self):
        self.runner.fail_sample='b1-s1-base';self.runner.collect()
        self.assertTrue(self.runner.export_legacy('memory_usage_test'));self.assertFalse(Path(self.owner.report_file).exists())
    def test_raw_boot_tamper_rejected_on_reuse(self):
        self.runner.collect();first=self.runner.run['samples'][0]
        item(first['raw_path'],'boot_id','wrong')
        self.assertFalse(self.runner.export_legacy('memory_info_test'))
    def test_parser_failure_propagated_without_report(self):
        self.runner.collect()
        from types import SimpleNamespace
        with patch('memory_rigor_runner.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout='',stderr='failed')):
            self.assertFalse(self.runner.export_legacy('memory_usage_test'))
        self.assertFalse(Path(self.owner.report_file).exists())
    def test_ion_after_all_base_samples(self):
        self.runner.cfg['ion_shrink']=True;self.assertTrue(self.runner.collect())
        for b in (1,2,3):
            calls=[(m,s) for m,s in self.runner.calls if f'-b{b}-' in s]
            intervention=next(i for i,(m,s) in enumerate(calls) if m=='ion')
            base=[i for i,(m,s) in enumerate(calls) if m=='snapshot' and s.endswith('-base')]
            self.assertEqual(len(base),5);self.assertGreater(intervention,max(base))
        self.assertTrue(any(a['metric'].endswith('__ion') for a in self.runner.run['aggregates']))
    def test_version_mismatch_warning(self):
        self.runner.cfg['expected_nevra']='different';self.assertTrue(self.runner.collect());self.assertTrue(self.runner.run['warnings'])
    def test_version_enforced_failure(self):
        self.runner.cfg.update(expected_nevra='different',enforce_version=True)
        self.assertFalse(self.runner.collect());self.assertEqual(self.runner.run['samples'],[])
    def test_failed_reboot_no_sample(self):
        self.owner.reboot_ok=False;self.assertFalse(self.runner.collect());self.assertEqual(self.runner.run['samples'],[])
    def test_db_normal_import_sidecar(self):
        from tpms_db import get_db_conn,save_file_to_db
        self.runner.collect();self.runner.export_legacy('memory_usage_test')
        c=get_db_conn(str(self.path/'db.sqlite'));save_file_to_db(c,self.owner.report_file,'tv',1)
        self.assertEqual(c.execute('select count(distinct snapshot_id) from memory_rigor_samples').fetchone()[0],15)
        self.assertEqual(c.execute("select count(*) from performance_data where metric_name='IdleMemoryUsage'").fetchone()[0],1)
        c.close()
    def test_detail_api_payload_and_no_old_threshold_change(self):
        from tpms_db import get_db_conn
        from tpms_db_queries import get_compare_detail_json
        c=get_db_conn(str(self.path/'db.sqlite'));save_run(c,run(rid='a'),'a',1);save_run(c,run(rid='b'),'b',1)
        result=json.loads(get_compare_detail_json(c,'a',1,'b',1));self.assertIn('memory_rigor',result)
        self.assertEqual(result['memory_rigor']['metrics'][0]['conclusion'],'在波动范围内，不作结论');c.close()

if __name__=='__main__':unittest.main()

class GateOrchestrationTests(unittest.TestCase):
    def test_gate_uses_target_cpu_deltas_and_records_all_probes(self):
        with tempfile.TemporaryDirectory() as d:
            owner=FakeOwner(Path(d),{'capture_policy':'gate'});runner=MemoryRigorRunner(owner)
            calls=[]
            def probe(mode,sid):
                self.assertEqual(mode,'probe');i=len(calls);calls.append(sid)
                p=Path(d)/sid;p.mkdir();capture(p,'boot1',sid)
                item(p,'uptime',str(300+30*i)+' 0')
                # 21 busy ticks per 100 ticks, independent of host time.
                item(p,'cpu.txt',f'cpu {21*i} 0 0 {79*i} 0 0 0 0 0 0\n')
                return p
            runner.capture=probe
            with patch('memory_rigor_runner.time.sleep') as sleep:
                gate=runner.gate(1,'gate-fixture')
            self.assertEqual(gate['uptime'],600);self.assertEqual(gate['status'],'steady')
            self.assertEqual(len(gate['sequence']),11);self.assertEqual(gate['sequence'][-1]['cpu'],21)
            self.assertEqual(sleep.call_count,10)
    def test_parser_error_marks_first_sample_invalid_in_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            owner=FakeOwner(Path(d));runner=FakeRunner(owner);runner.calls=[];runner.collect()
            from types import SimpleNamespace
            with patch('memory_rigor_runner.subprocess.run',return_value=SimpleNamespace(returncode=7,stdout='',stderr='invalid')):
                self.assertFalse(runner.export_legacy('memory_info_test'))
            saved=json.loads((Path(d)/'memory_rigor.json').read_text())
            self.assertFalse(saved['samples'][0]['valid']);self.assertTrue(run_quality(saved)['valid'])
