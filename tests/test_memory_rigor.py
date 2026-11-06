import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone'))
sys.path.insert(0,str(ROOT/'db'))
from memory_rigor import *
from memory_rigor_runner import checked_script_command, MemoryRigorRunner
from memory_fixture import capture,item,stat,sample,run,MEMINFO,MEMPS,ROLLUP


class GateTests(unittest.TestCase):
    def rows(self,cpu=21):
        return [dict(boot_id='b',uptime=330+i*30,MemTotal=100000,MemAvailable=50000+i,SwapUsed=1000,cpu=cpu) for i in range(10)]
    def test_defaults_off(self):
        self.assertFalse(config()['enabled']);self.assertEqual((config()['boots'],config()['samples']),(1,1))
    def test_invalid_config(self):
        for cfg in ({'boots':0},{'coverage_min':1.1},{'typo':1},{'enabled':'false'}):
            with self.assertRaises(ValueError):config(cfg)
    def test_steady_inclusive_cpu(self):self.assertEqual(gate_decision(self.rows(),config(),0)['status'],'steady')
    def test_memory_range_strict(self):
        rows=self.rows();rows[-1]['MemAvailable']=51000
        self.assertEqual(gate_decision(rows,config(),0)['status'],'waiting')
    def test_min_uptime(self):
        rows=self.rows()
        for r in rows:r['uptime']-=30
        self.assertEqual(gate_decision(rows,config(),0)['status'],'waiting')
    def test_insufficient(self):self.assertEqual(gate_decision(self.rows()[:9],config(),0)['reason'],'insufficient_samples')
    def test_cpu_high(self):self.assertEqual(gate_decision(self.rows(21.1),config(),0)['status'],'waiting')
    def test_limit_uses_target_elapsed(self):
        rows=self.rows(100);rows[-1]['uptime']=1860
        self.assertEqual(gate_decision(rows,config(),60)['reason'],'按上限采集')
    def test_boot_change(self):
        rows=self.rows();rows[-1]['boot_id']='different'
        self.assertEqual(gate_decision(rows,config(),0)['status'],'error')
    def test_gap_breaks_window(self):
        rows=self.rows();rows[5]['uptime']+=61
        self.assertEqual(gate_decision(rows,config(),0)['status'],'waiting')
    def test_cpu_guest_excluded(self):self.assertEqual(cpu_counters('cpu 10 0 5 80 5 0 0 0 9 0'),(100,85))
    def test_cpu_delta(self):self.assertEqual(cpu_percent((100,80),(200,159)),21)
    def test_cpu_reset(self):
        with self.assertRaises(ValueError):cpu_percent((100,80),(90,70))


class ParserTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.identity=capture(self.path)
    def tearDown(self):self.tmp.cleanup()
    def parse(self,cfg=None):return parse_snapshot(self.path,self.identity,config(cfg))
    def test_normal(self):
        s=self.parse();self.assertTrue(s['valid'],s['errors']);self.assertEqual(s['metrics']['Rigor_ProcessPssSwapPss'],2200)
        self.assertEqual(s['metrics']['Rigor_ZramUsed'],60);self.assertEqual(s['processes'][0]['starttime'],100)
    def test_empty_memps(self):
        item(self.path,'memps.txt','');self.assertFalse(self.parse()['valid'])
    def test_missing_meminfo_field(self):
        item(self.path,'meminfo.txt',MEMINFO.replace('Slab: 2000 kB\n',''));self.assertFalse(self.parse()['valid'])
    def test_bad_unit(self):
        item(self.path,'meminfo.txt',MEMINFO.replace('kB','MB'));self.assertFalse(self.parse()['valid'])
    def test_process_disappears(self):
        item(self.path,'proc/2/stat_end','',1);s=self.parse()
        self.assertFalse(s['valid']);self.assertEqual(s['coverage'],0.5);self.assertTrue(s['processes'][1]['errors'])
    def test_permission_failure(self):
        item(self.path,'proc/1/smaps_rollup','',13);self.assertFalse(self.parse()['valid'])
    def test_pid_reuse(self):
        item(self.path,'proc/1/stat_end',stat(1,101));self.assertTrue(self.parse()['valid']);self.assertEqual(self.parse()['exited_processes'][0]['pid'],1)
    def test_coverage_config(self):
        item(self.path,'proc/1/smaps_rollup','',1);s=self.parse({'coverage_min':0.5})
        self.assertTrue(s['valid']);self.assertFalse(s['inventory_complete']);self.assertEqual(s['metrics']['Rigor_ProcessPssSwapPss'],1100)
    def test_boot_mismatch(self):
        item(self.path,'boot_id_end','other');self.assertFalse(self.parse()['valid'])
    def test_snapshot_mismatch(self):
        item(self.path,'snapshot_id','wrong');self.assertFalse(self.parse()['valid'])
    def test_smaps_full_and_rollup(self):
        self.assertEqual(parse_smaps(ROLLUP+ROLLUP)['PssSwapPss'],2200)
    def test_smaps_missing_swap(self):
        with self.assertRaises(ValueError):parse_smaps('Pss: 123 kB\nPrivate_Dirty: 1 kB\n')
    def test_stat_parentheses(self):self.assertEqual(parse_stat(stat(7,9999)),9999)
    def test_memps_missing_total(self):
        with self.assertRaises(ValueError):parse_memps(MEMPS.split('TOTAL:')[0])
    def test_memps_gpu_separate(self):
        mp=parse_memps(MEMPS);self.assertEqual(mp['totals']['PSS'],3000);self.assertEqual(mp['totals']['3D'],5)
    def test_empty_vmalloc(self):
        item(self.path,'vmallocinfo.txt','');self.assertFalse(self.parse()['valid'])
    def test_zram_bad_value(self):
        item(self.path,'zram/zram0','1 bad 3');self.assertFalse(self.parse()['valid'])


class StorageCompareTests(unittest.TestCase):
    def test_two_level_aggregation(self):
        a=aggregate(run())[1] if aggregate(run())[0]['metric']=='Rigor_AccountedUsed' else aggregate(run())[0]
        self.assertEqual(a['boot_medians'],{'1':1100,'2':1110});self.assertEqual(a['mean'],1105);self.assertEqual(a['range'],10)
    def test_invalid_excluded(self):
        r=run();r['samples'][0]['valid']=False;r['samples'][0]['metrics']['Rigor_ProcessPssSwapPss']=999999
        self.assertEqual(next(x for x in aggregate(r) if x['metric']=='Rigor_ProcessPssSwapPss')['boot_medians']['1'],1150)
    def test_all_invalid_no_aggregates(self):
        r=run()
        for s in r['samples']:s['valid']=False
        self.assertEqual(aggregate(r),[])
    def test_storage_preserves_samples(self):
        c=sqlite3.connect(':memory:');r=run();save_run(c,r,'tv',1);save_run(c,r,'tv',1)
        self.assertEqual(c.execute('select count(*) from memory_rigor_samples').fetchone()[0],18)
        self.assertEqual(c.execute('select count(*) from memory_rigor_gates').fetchone()[0],2)
    def test_invalid_stored_null(self):
        c=sqlite3.connect(':memory:');r=run();r['samples'][0].update(valid=False,errors=['bad'],invalid_reason='bad')
        save_run(c,r,'tv',1)
        self.assertEqual(c.execute('select distinct value from memory_rigor_samples where valid=0').fetchall(),[(None,)])
    def test_run_id_collision_rejected(self):
        c=sqlite3.connect(':memory:');r=run();save_run(c,r,'tv',1)
        with self.assertRaises(ValueError):save_run(c,r,'tv',2)
    def test_duplicate_snapshot_rejected(self):
        r=run();r['samples'][1]['snapshot_id']=r['samples'][0]['snapshot_id']
        with self.assertRaises(ValueError):validate_run(r)
    def test_reused_boot_rejected(self):
        r=run()
        for s in r['samples']:s['boot_id']='same'
        with self.assertRaises(ValueError):validate_run(r)
    def test_exceeds_both_ranges(self):
        c=compare_runs(run(((2000,2001,2002),(2010,2011,2012)),'a'),run(rid='b'))
        self.assertEqual(c['metrics'][0]['conclusion'],'差异超出波动')
    def test_within_range(self):
        c=compare_runs(run(rid='a'),run(rid='b'));self.assertEqual(c['metrics'][0]['conclusion'],'在波动范围内，不作结论')
    def test_exceeds_only_one_range_not_enough(self):
        a=run(((1000,1000,1000),(1400,1400,1400)),'a');b=run(((1000,1000,1000),(1010,1010,1010)),'b')
        self.assertEqual(compare_runs(a,b)['metrics'][0]['conclusion'],'在波动范围内，不作结论')
    def test_invalid_side_blocks(self):
        a=run();a['samples'][0].update(valid=False,errors=['bad'],invalid_reason='bad')
        self.assertEqual(compare_runs(a,run(rid='b'))['metrics'],[])
    def test_missing_samples_blocks(self):
        a=run();a['samples'].pop();self.assertFalse(run_quality(a)['valid'])
    def test_one_sided_and_decomposition(self):
        a=run(rid='a');b=run(rid='b')
        for s in a['samples']:s['processes'][0]['comm']='only-a'
        c=compare_runs(a,b);self.assertIsNone(c['process_groups']['only_a']['rows'][0]['b'])
        d=c['decomposition'];self.assertEqual(d['common_process_delta_kB']+d['one_side_contribution_kB']+d['system_residual_delta_kB'],d['used_mem_delta_kB'])
    def test_incomplete_inventory_blocks_attribution(self):
        a=run();a['samples'][0]['inventory_complete']=False
        self.assertIsNone(compare_runs(a,run(rid='b'))['process_groups'])
    def test_ion_not_mixed(self):
        r=run();r['samples'].append(sample(value=999999,phase='ion'))
        self.assertEqual(next(x for x in aggregate(r) if x['metric']=='Rigor_ProcessPssSwapPss' and x['phase']=='base')['mean'],1105)
    def test_no_rigor_tables_old_comparison(self):
        from tpms_db_queries import get_memory_rigor_comparison
        self.assertIsNone(get_memory_rigor_comparison(sqlite3.connect(':memory:'),'a',1,'b',1))


class ExecutionTests(unittest.TestCase):
    def test_empty_uep_payload_rejected(self):
        with tempfile.NamedTemporaryFile() as f:
            r=subprocess.run(['bash','-c',checked_script_command(f.name,[])],capture_output=True)
            self.assertEqual(r.returncode,125)
    def test_uep_quoting_and_exit(self):
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write('printf "%s" "$1"; exit 7');f.flush()
            r=subprocess.run(['bash','-c',checked_script_command(f.name,['a; echo unsafe'])],capture_output=True,text=True)
            self.assertEqual(r.returncode,7);self.assertEqual(r.stdout,'a; echo unsafe')
    def test_checked_transport_captures_target_rc(self):
        # Extract just the method: importing checktap/device must not touch a board.
        tree=ast.parse((ROOT/'standalone/tpms_util.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='device')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='executeCmd_result')
        import time,signal,re
        ns=dict(subprocess=subprocess,os=os,time=time,signal=signal,re=re)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'method','exec'),ns)
        with tempfile.TemporaryDirectory() as d:
            fake=Path(d)/'sdb';fake.write_text("#!/bin/bash\nbash -c \"$4\" | sed 's/$/\\r/'\n");fake.chmod(0o755)
            obj=type('Device',(),{'_CMD':str(fake),'_dev_serial':'unused'})()
            result=ns['executeCmd_result'](obj,'printf payload; exit 7',2)
            self.assertEqual(result['returncode'],7,result);self.assertEqual(result['stdout'],'payload')
            self.assertIn('TPMS_RC_',result['raw_stdout']);self.assertIn('\r\n',result['raw_stdout'])
    def test_target_shell_syntax(self):
        for p in (ROOT/'performance/script').glob('*memory*/target/*.sh'):
            self.assertEqual(subprocess.run(['bash','-n',str(p)],capture_output=True).returncode,0,str(p))

if __name__=='__main__':unittest.main()

class CheckedTransferTests(unittest.TestCase):
    def test_transfer_nonzero_rc_and_stderr_preserved(self):
        tree=ast.parse((ROOT/'standalone/tpms_util.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='device')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='transfer_result')
        import time,signal
        ns=dict(subprocess=subprocess,os=os,time=time,signal=signal)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'transfer','exec'),ns)
        with tempfile.TemporaryDirectory() as d:
            fake=Path(d)/'sdb';fake.write_text('#!/bin/bash\necho copy-failed >&2\nexit 2\n');fake.chmod(0o755)
            obj=type('Device',(),{'_CMD':str(fake),'_dev_serial':'unused'})()
            result=ns['transfer_result'](obj,'pull','source','destination',1)
            self.assertEqual(result['returncode'],2);self.assertIn('copy-failed',result['stderr'])
    def test_missing_operation_timing_is_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            identity=capture(d);(Path(d)/'memps.txt.start').unlink()
            self.assertFalse(parse_snapshot(d,identity,config())['valid'])
