"""Offline regression coverage for in-place memory rigor corrections."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'standalone'),str(ROOT/'db')]
from memory_rigor import *
from memory_rigor_runner import MemoryRigorRunner
from memory_fixture import capture,item,stat,run,sample
from test_memory_runner import FakeOwner,FakeRunner
from sdb_output_fixture import sdb_result


def stat_fields(pid=1,start=100,flags=0,ppid=9):
    text=stat(pid,start);end=text.rfind(')');fields=text[end+2:].split()
    fields[1]=str(ppid);fields[6]=str(flags)
    return text[:end+2]+' '.join(fields)+'\n'


class ProcessRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.identity=capture(self.path)
    def tearDown(self):self.tmp.cleanup()
    def parse(self):return parse_snapshot(self.path,self.identity,config())
    def gone(self,name):
        item(self.path,name,'',1);(self.path/(name+'.errno')).write_text('ENOENT')
    def test_flags_ppid_and_starttime_parsed(self):
        f=parse_stat_fields(stat_fields(flags=2097152,ppid=42));self.assertEqual(f,dict(flags=2097152,ppid=42,starttime=100))
    def test_kernel_excluded_from_denominator_and_total(self):
        item(self.path,'proc/2/stat',stat_fields(2,flags=0x00200000));item(self.path,'proc/2/smaps_rollup','',13)
        s=self.parse();self.assertTrue(s['valid']);self.assertEqual(s['kernel_threads'],1)
        self.assertEqual(s['coverage_denominator'],1);self.assertEqual(s['coverage'],1);self.assertTrue(s['inventory_complete'])
        self.assertEqual(s['metrics']['Rigor_ProcessPssSwapPss'],1100)
    def test_initial_enoent_excluded(self):
        self.gone('proc/2/stat');s=self.parse();self.assertTrue(s['valid']);self.assertEqual(s['coverage'],1)
        self.assertTrue(s['inventory_complete']);self.assertEqual(len(s['exited_processes']),1)
    def test_initial_esrch_excluded(self):
        self.gone('proc/2/stat');(self.path/'proc/2/stat.errno').write_text('ESRCH');self.assertTrue(self.parse()['valid'])
    def test_initial_eacces_not_excluded(self):
        item(self.path,'proc/2/stat','',13);s=self.parse();self.assertFalse(s['valid']);self.assertEqual(s['coverage_denominator'],2)
    def test_end_enoent_excluded_with_identity(self):
        self.gone('proc/2/stat_end');s=self.parse();self.assertTrue(s['valid']);self.assertEqual(s['exited_processes'][0]['comm'],'app2')
    def test_starttime_changed_excluded(self):
        item(self.path,'proc/2/stat_end',stat_fields(2,101));s=self.parse()
        self.assertTrue(s['valid']);self.assertTrue(s['inventory_complete']);self.assertEqual(s['exited_processes'][0]['classification'],'exited')
    def test_permission_error_still_invalid(self):
        item(self.path,'proc/2/smaps_rollup','',13);self.assertFalse(self.parse()['valid'])
    def test_empty_user_inventory_not_fabricated_zero(self):
        for pid in (1,2):item(self.path,f'proc/{pid}/stat',stat_fields(pid,flags=0x00200000))
        s=self.parse();self.assertFalse(s['valid']);self.assertIsNone(s['metrics']['Rigor_ProcessPssSwapPss'])
    def test_used_mem_definition(self):
        s=self.parse();self.assertEqual(s['metrics']['Rigor_UsedMem'],40000);self.assertEqual(s['metrics']['Rigor_AccountedUsed'],51000)
    def test_collector_descendants_excluded_by_shell(self):
        # Execute the actual enumeration block against synthetic proc files only.
        script=(ROOT/'performance/script/memory_usage_test/target/memory_rigor_capture.sh').read_text()
        block=script[script.index('    pids=();'):script.index('    record excluded_pids')]
        proc=self.path/'synthetic_proc';proc.mkdir()
        for pid,parent in [(10,1),(11,10),(12,11),(1,0)]:
            (proc/str(pid)).mkdir();(proc/str(pid)/'stat').write_text(stat_fields(pid,ppid=parent))
        block=block.replace('/proc/',str(proc)+'/').replace('omitted[$$]=1','omitted[10]=1')
        result=subprocess.run(['bash','-c','set -u\n'+block+'\nprintf "%s\\n" "${selected[@]}"'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'1')
    def test_kernel_and_exited_not_grouped(self):
        a=run();b=run(rid='b')
        for s in a['samples']:s['processes'] += [dict(pid=99,classification='kernel',valid=False),dict(pid=98,classification='exited',valid=False)]
        c=compare_runs(a,b);self.assertEqual(len(c['process_groups']['common']['rows']),1)
    def test_majority_exit_warning_and_minority_no_warning(self):
        a=run()
        for s in a['samples'][:2]:s['exited_processes']=[dict(comm='flapping',exe='/bin/flapping')]
        self.assertTrue(any('多数样本' in w for w in run_quality(a)['warnings']))
        a['samples'][1]['exited_processes']=[];self.assertFalse(run_quality(a)['warnings'])


class PolicyRevisionTests(unittest.TestCase):
    def rows(self,uptime=1800,cpu=50,unstable=False):
        return [dict(boot_id='b',uptime=uptime-270+30*i,MemTotal=100000,MemAvailable=60000+(2000*i if unstable else i),SwapUsed=100,cpu=cpu) for i in range(10)]
    def test_fixed_default_and_tv(self):
        self.assertEqual(config()['capture_policy'],'fixed_uptime')
        tv=json.loads((ROOT/'standalone/tpms_cfg_10.0-tv-kantsu2e.json').read_text())['memory_rigor']
        self.assertEqual(tv['capture_policy'],'fixed_uptime');self.assertTrue(tv['initial_gate']);self.assertFalse(tv['ion_shrink'])
    def test_fixed_does_not_collect_on_early_steady(self):
        self.assertEqual(capture_decision(self.rows(900,10),config(),60)['status'],'waiting')
    def test_fixed_cpu_high_still_collects_memory_stable(self):
        d=capture_decision(self.rows(),config(),60)
        self.assertEqual(d['status'],'fixed');self.assertTrue(d['memory_stable']);self.assertFalse(d['cpu_met'])
    def test_memory_condition_independent_of_missing_cpu_interval(self):
        rows=self.rows();rows[0]['cpu']=None
        d=capture_decision(rows,config(),60)
        self.assertTrue(d['memory_stable']);self.assertFalse(d['cpu_met']);self.assertEqual(d['status'],'fixed')
    def test_fixed_unstable_warning(self):
        d=capture_decision(self.rows(unstable=True),config(),60);self.assertEqual(d['reason'],'采集时内存未平稳')
    def test_fixed_insufficient_at_point_marked_unstable(self):
        self.assertEqual(capture_decision(self.rows()[-1:],config(),1790)['status'],'unstable')
    def test_gate_retains_early_capture(self):
        self.assertEqual(capture_decision(self.rows(900,10),config({'capture_policy':'gate'}),60)['status'],'steady')
    def test_policy_and_uptime_mismatch_warnings(self):
        a=run();b=run(rid='b');b['config']['capture_policy']='gate'
        self.assertTrue(comparison_warnings(a,b));b['config']['capture_policy']='fixed_uptime';b['config']['capture_uptime_s']=1200
        self.assertTrue(comparison_warnings(a,b))
    def test_limit_unstable_and_asymmetric_gate_warning(self):
        a=run();b=run(rid='b');a['config']['capture_policy']=b['config']['capture_policy']='gate'
        a['gates'][0].update(status='limit',reason='按上限采集')
        w=comparison_warnings(a,b);self.assertTrue(any('按上限' in x for x in w));self.assertTrue(any('状态不同' in x for x in w))
        a['gates'][0].update(status='unstable',reason='采集时内存未平稳');self.assertTrue(any('未平稳' in x for x in comparison_warnings(a,b)))
    def test_initial_gate_disabled_no_device_access(self):
        with tempfile.TemporaryDirectory() as d:
            r=MemoryRigorRunner(FakeOwner(Path(d)));r.prepare=lambda: self.fail('device accessed')
            self.assertTrue(r.standalone_gate())
    def test_initial_gate_cleanup_failure_propagates(self):
        with tempfile.TemporaryDirectory() as d:
            r=FakeRunner(FakeOwner(Path(d),{'initial_gate':True}));r.calls=[]
            r.cleanup=lambda *args: (_ for _ in ()).throw(RuntimeError('cleanup failed'))
            self.assertFalse(r.standalone_gate())
    def test_fixed_sequence_first_satisfied(self):
        with tempfile.TemporaryDirectory() as d:
            r=MemoryRigorRunner(FakeOwner(Path(d)));calls=[]
            def probe(mode,sid):
                i=len(calls);calls.append(sid);p=Path(d)/sid;p.mkdir();capture(p,'b',sid)
                item(p,'uptime',f'{300+30*i} 0');item(p,'cpu.txt',f'cpu {10*i} 0 0 {90*i} 0 0 0 0\n');return p
            r.capture=probe
            with patch('memory_rigor_runner.time.sleep'):g=r.gate(1,'fixedtest')
            self.assertEqual(g['uptime'],1800);self.assertEqual(g['first_satisfied_uptime'],600);self.assertEqual(len(g['sequence']),51)


class QualityRevisionTests(unittest.TestCase):
    def test_three_of_five_valid_per_boot(self):
        a=run(((1,2,3,4,5),(1,2,3,4,5)))
        for s in a['samples']:
            if s['sample_index']>3:s.update(valid=False,invalid_reason='bad',errors=['bad'])
        q=run_quality(a);self.assertTrue(q['valid']);self.assertEqual(q['per_boot'][0]['invalid'],2)
        self.assertEqual(aggregate(a)[0]['valid_samples'],6)
    def test_two_valid_insufficient_even_other_boot_good(self):
        a=run(((1,2,3,4,5),(1,2,3,4,5)))
        for s in a['samples'][:3]:s.update(valid=False,invalid_reason='bad',errors=['bad'])
        self.assertFalse(run_quality(a)['valid'])
    def test_missing_gate_invalid(self):
        a=run();a['gates'].pop()
        with self.assertRaises(ValueError):run_quality(a)
    def test_missing_gate_without_samples_invalid(self):
        a=run();a['gates'].pop();a['samples']=a['samples'][:3];self.assertFalse(run_quality(a)['valid'])
    def test_invalid_samples_not_in_cohort(self):
        a=run(((1,2,3,4,5),(1,2,3,4,5)));b=copy.deepcopy(a);b['run_id']='b'
        for s in b['samples']:s['run_id']='b'
        a['samples'][0].update(valid=False,inventory_complete=False,invalid_reason='bad',errors=['bad'])
        self.assertIsNotNone(compare_runs(a,b)['process_groups'])
    def test_used_mem_decomposition_not_accounted(self):
        a=run();b=run(rid='b')
        for s in a['samples']:s['metrics']['Rigor_UsedMem']+=100;s['metrics']['Rigor_AccountedUsed']+=999
        d=compare_runs(a,b)['decomposition'];self.assertEqual(d['used_mem_delta_kB'],100)
        self.assertEqual(d['common_process_delta_kB']+d['one_side_contribution_kB']+d['system_residual_delta_kB'],100)
    def test_smoke_requires_explicit_min_two(self):
        a=run(((1,2),));self.assertFalse(run_quality(a)['valid'])
        a['config']['min_valid_samples_per_boot']=2;self.assertTrue(run_quality(a)['valid'])
    def test_osrelease_version_identity_and_complete_tools(self):
        identity=image_identity('ID=tizen\nVERSION_ID="10.0"\nBUILD_ID=abc\nOTHER=kept-in-tools\n')
        self.assertEqual(json.loads(identity),{'ID':'tizen','VERSION_ID':'10.0','BUILD_ID':'abc'})
    def test_osrelease_no_version_fails(self):
        with self.assertRaises(ValueError):image_identity('ID=tizen')
    def test_run_cleanup_failure_is_false(self):
        with tempfile.TemporaryDirectory() as d:
            r=FakeRunner(FakeOwner(Path(d)));r.calls=[]
            r.cleanup=lambda *args: (_ for _ in ()).throw(RuntimeError('cleanup failed'))
            self.assertFalse(r.collect());self.assertIn('cleanup failed',r.run['errors'])
    def test_fallback_warning_in_run_and_comparison(self):
        with tempfile.TemporaryDirectory() as d:
            owner=FakeOwner(Path(d));r=FakeRunner(owner);r.calls=[]
            def install(*args,**kwargs):
                owner._memory_tool_url='fixture://latest/memps.rpm';owner._memory_tool_fallback_reason='snapshot 404';return True
            owner.install_package_from_repo=install
            self.assertTrue(r.collect());self.assertTrue(any('latest' in w for w in r.run['warnings']))
            self.assertTrue(any('snapshot 404' in w for w in compare_runs(r.run,r.run)['warnings']))
    def test_method_mismatch_old_rows_warn_without_numeric_change(self):
        from tpms_db import SCHEMA_SQL
        from tpms_db_queries import get_compare_detail_json
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;c.executescript(SCHEMA_SQL)
        c.executemany('insert into performance_data(job_name,build_number,test_name,metric_name,metric_value,metric_unit) values (?,?,?,?,?,?)', [('a',1,'Idle Memory Usage','IdleMemoryUsage',488,'MB'),('b',1,'Idle Memory Usage','IdleMemoryUsage',480,'MB'),('a',1,'Boot','BootingTime',100,'ms'),('b',1,'Boot','BootingTime',200,'ms')])
        before=json.loads(get_compare_detail_json(c,'a',1,'b',1));save_run(c,run(),'a',1)
        after=json.loads(get_compare_detail_json(c,'a',1,'b',1))
        for x,y in zip(before['rows'],after['rows']):
            if y.get('metric_name')=='IdleMemoryUsage':self.assertIn('测量方法不同',y.pop('method_warning'))
            self.assertEqual(x,y)
    def test_status_translation_and_alert_rendering(self):
        js=(ROOT/'db/static/js/dashboard.js').read_text();snippet=js[js.index('function memoryGateLabel'):]
        self.assertIn("steady_criteria_met: '满足判据'",snippet)
        self.assertIn('role="alert"',snippet)



class ArchiveRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.owner=FakeOwner(self.path);self.r=MemoryRigorRunner(self.owner)
        raw=self.path/'raw';raw.mkdir();capture(raw,'b','snap')
        self.archive=self.path/'source.tar'
        with tarfile.open(self.archive,'w') as t:t.add(raw,arcname='.')
        self.count=sum(p.is_file() for p in raw.rglob('*'));self.badsha=False;self.pull_fail=False;self.commands=[];self.pulls=[]
        self.owner.executeCmd_result=self.execute;self.owner.transfer_result=self.transfer
    def tearDown(self):self.tmp.cleanup()
    def execute(self,cmd,timeout):
        self.commands.append(cmd)
        if cmd.startswith('rm '):return sdb_result()
        sha='0'*64 if self.badsha else hashlib.sha256(self.archive.read_bytes()).hexdigest()
        return sdb_result(f'TPMS_ARCHIVE {sha} 600 605 605 606 {self.count}\n')
    def transfer(self,direction,source,dest,timeout):
        self.pulls.append((direction,source,dest))
        if self.pull_fail:return dict(returncode=2,stdout='',stderr='failed')
        shutil.copyfile(self.archive,dest);return dict(returncode=0,stdout='',stderr='')
    def test_single_archive_hash_unpack_cleanup_and_timing(self):
        p=self.r.capture('snapshot','snap');self.assertTrue((p/'memps.txt').is_file())
        self.assertEqual(len(self.pulls),1);self.assertTrue(self.pulls[0][1].endswith('.tar'));self.assertNotIn('/.',self.pulls[0][1])
        d=self.r.transfers[0];self.assertEqual(d['board_seconds'],5);self.assertEqual(d['pack_seconds'],1);self.assertEqual(d['file_count'],self.count)
        self.assertTrue(d['cleanup']['verified']);self.assertTrue(any(c.startswith('rm -rf --') for c in self.commands))
    def test_hash_mismatch_never_unpacks(self):
        self.badsha=True
        with self.assertRaisesRegex(RuntimeError,'SHA-256'):self.r.capture('snapshot','snap')
        self.assertFalse((self.r.root/'snap/memps.txt').exists())
    def test_archive_receipt_real_sdb_format(self):
        self.r.capture('snapshot','snap')
        result=json.loads((self.r.root/'commands/snap.json').read_text())
        sha=hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.assertEqual(result['stdout'],f'TPMS_ARCHIVE {sha} 600 605 605 606 {self.count}\n')
        self.assertIn('\r\n\r\nTPMS_RC_',result['raw_stdout'])
        self.assertTrue(self.r.transfers[0]['verified'])
    def test_pull_failure_stops(self):
        self.pull_fail=True
        with self.assertRaisesRegex(RuntimeError,'pull failed'):self.r.capture('snapshot','snap')
    def test_tar_absence_stops_without_pull(self):
        self.owner.executeCmd_result=lambda *args:sdb_result(rc=2,stderr='tar unavailable')
        with self.assertRaises(RuntimeError):self.r.capture('snapshot','snap')
        self.assertEqual(self.pulls,[])
    def test_archive_traversal_rejected(self):
        with tarfile.open(self.archive,'w') as t:
            m=tarfile.TarInfo('../escape');m.size=1;t.addfile(m,io.BytesIO(b'x'))
        self.count=1
        with self.assertRaisesRegex(RuntimeError,'unsafe archive'):self.r.capture('snapshot','snap')
    def test_archive_symlink_rejected(self):
        with tarfile.open(self.archive,'w') as t:
            m=tarfile.TarInfo('escape');m.type=tarfile.SYMTYPE;m.linkname='/tmp';t.addfile(m)
        self.count=0
        with self.assertRaisesRegex(RuntimeError,'unsafe archive'):self.r.capture('snapshot','snap')
    def test_cleanup_scoped_and_verified(self):
        self.assertTrue(self.r.cleanup()['verified'])
        with self.assertRaises(ValueError):self.r.cleanup('/opt/usr/tpms/result/memory_rigor/other')
        self.owner.executeCmd_result=lambda *args:sdb_result(rc=1,stderr='not deleted')
        with self.assertRaises(RuntimeError):self.r.cleanup()
    def test_no_directory_pull_in_source(self):
        self.assertNotIn("remote+'/.',",(ROOT/'standalone/memory_rigor_runner.py').read_text())
        text=(ROOT/'performance/script/memory_usage_test/target/memory_rigor_capture.sh').read_text()
        self.assertIn('command -v tar',text);self.assertIn('pack_rc=$?',text)

if __name__=='__main__':unittest.main()

class AdditionalIntegrationTests(unittest.TestCase):
    def test_target_permission_not_misclassified_as_disappearance(self):
        text=(ROOT/'performance/script/memory_usage_test/target/memory_rigor_capture.sh').read_text()
        function=text[text.index('record() {'):text.index('start=$(stamp)')]
        with tempfile.TemporaryDirectory() as d:
            script='out='+repr(d)+'\noperation_failed=0\nstamp(){ printf "600\\n"; }\ncat(){ printf "cat: Permission denied\\n" >&2; return 1; }\n'+function+'\nrecord proc/1/stat cat /absent\n'
            r=subprocess.run(['bash','-c',script],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertFalse((Path(d)/'proc/1/stat.errno').exists())
            script=script.replace('Permission denied','No such file or directory')
            self.assertEqual(subprocess.run(['bash','-c',script],capture_output=True).returncode,0)
            self.assertEqual((Path(d)/'proc/1/stat.errno').read_text().strip(),'ENOENT')
    def test_original_installer_records_latest_url_and_reason(self):
        import logging,re
        tree=ast.parse((ROOT/'standalone/standalone.py').read_text())
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='install_package_from_repo')
        ns=dict(os=os,logging=logging,re=re,coded_str=lambda x,**kw:x)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'installer','exec'),ns)
        device=SimpleNamespace(refresh_tcp_connection=lambda:None,pushFile=lambda *x:None,executeCmd_timeout=lambda *x:1)
        owner=SimpleNamespace(_device=device,_rpm_query_installed=lambda p:False,_snapshot_id='build_123',memory_rigor={'enabled':True},
            _testinfo={'test_profile_data':{'repo_url':'https://fixture/latest/','snapshot_serverid':'x','snapshot_serverpasswd':'x'}},
            target_input_path='/tmp',_rpm_install_marker_ok=lambda p:True)
        commands=[]
        with tempfile.TemporaryDirectory() as d:
            previous=os.getcwd();os.chdir(d)
            def command(cmd):
                commands.append(cmd)
                if '-O index.html' in cmd:
                    Path('index.html').write_text(' memps-fixture.rpm size\n' if '/latest/' in cmd else '')
                    return 0 if '/latest/' in cmd else 256
                if cmd.startswith('wget '):Path('memps-fixture.rpm').write_text('fixture')
                return 0
            try:
                with patch('os.system',side_effect=command):self.assertTrue(ns['install_package_from_repo'](owner,'memps'))
            finally:os.chdir(previous)
        self.assertEqual(owner._memory_tool_url,'https://fixture/latest/memps-fixture.rpm')
        self.assertIn('rc=256',owner._memory_tool_fallback_reason)
    def test_prepare_root_failure_before_push(self):
        with tempfile.TemporaryDirectory() as d:
            owner=FakeOwner(Path(d));runner=MemoryRigorRunner(owner)
            owner.executeCmd_result=lambda cmd,t:sdb_result('1000\n' if cmd=='id -u' else '')
            owner.transfer_result=lambda *x:self.fail('pushed before root validation')
            with self.assertRaisesRegex(RuntimeError,'requires root'):runner.prepare()
    def test_run_markers_and_full_osrelease(self):
        with tempfile.TemporaryDirectory() as d:
            r=FakeRunner(FakeOwner(Path(d)));r.calls=[];self.assertTrue(r.collect())
            self.assertEqual(r.run['memory_method'],'rigor_v2');self.assertEqual(r.run['capture_policy'],'fixed_uptime')
            self.assertEqual(r.run['capture_uptime_s'],1800);self.assertEqual(json.loads(r.run['image_id']),{'BUILD_ID':'test-image'})
            self.assertEqual(r.run['tools'][0]['os_release'],'BUILD_ID=test-image')
    def test_process_exclusions_retained_in_db_payload(self):
        a=run();a['samples'][0]['processes'].append(dict(pid=8,valid=False,classification='kernel',flags=0x00200000,ppid=2,starttime=10))
        c=sqlite3.connect(':memory:');save_run(c,a,'a',1)
        row=c.execute('select detail from memory_rigor_processes where pid=8').fetchone()
        self.assertEqual(json.loads(row[0])['flags'],0x00200000)
