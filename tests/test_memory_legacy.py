import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
FX=ROOT/'tests/fixtures/memory_rigor'
CASES=[('memory_usage_test','get_used_memory.py'),('process_memory_usage_test','get_process_memory_usage.py'),('memory_info_test','get_memory_info.py')]


class LegacyCompatibilityTests(unittest.TestCase):
    def command(self,case,file,image,out,strict=False):
        d=FX/image
        cmd=[sys.executable,str(ROOT/'performance/script'/case/'host'/file),case,'success']
        if case=='memory_info_test':cmd += ['10.0-tv-kantsu2e',str(d/'meminfo.txt'),str(d/'vmallocinfo.txt'),str(d/'memps.txt')]
        else:cmd += [str(d/'memps.txt')]
        cmd+=['-o',str(out)]
        if strict:cmd+=['--strict']
        return cmd
    def test_legacy_output_bytes_both_images(self):
        for image in ('gcc_baseline','llvm_round3'):
            for case,file in CASES:
                with self.subTest(image=image,case=case),tempfile.TemporaryDirectory() as d:
                    out=Path(d)/'report.txt';r=subprocess.run(self.command(case,file,image,out),capture_output=True)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(out.read_bytes(),(FX/image/(case+'.expected')).read_bytes())
    def test_strict_valid_legacy_metric_meaning_unchanged(self):
        for image in ('gcc_baseline','llvm_round3'):
            for case,file in CASES:
                with self.subTest(image=image,case=case),tempfile.TemporaryDirectory() as d:
                    out=Path(d)/'report.txt';r=subprocess.run(self.command(case,file,image,out,True),capture_output=True)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(out.read_bytes(),(FX/image/(case+'.expected')).read_bytes())
    def test_strict_empty_never_emits_zero_or_partial_rows(self):
        for case,file in CASES:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as d:
                out=Path(d)/'report.txt';empty=Path(d)/'empty';empty.write_text('')
                cmd=self.command(case,file,'gcc_baseline',out,True)
                cmd=[str(empty) if x.endswith('/memps.txt') else x for x in cmd]
                r=subprocess.run(cmd,capture_output=True)
                self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
    def test_strict_missing_memory_field_clean_failure(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.txt';mi=Path(d)/'meminfo.txt'
            mi.write_text('MemTotal: 1000 kB\n')
            cmd=self.command(*CASES[2],'gcc_baseline',out,True)
            cmd=[str(mi) if x.endswith('/meminfo.txt') else x for x in cmd]
            r=subprocess.run(cmd,capture_output=True)
            self.assertNotEqual(r.returncode,0);self.assertNotIn(b'Traceback',r.stderr);self.assertFalse(out.exists())
    def test_unmodified_profiles_and_disabled_shell_body(self):
        guard=json.loads((FX/'legacy_guards.json').read_text())
        for name,expected in guard['files'].items():
            data=(ROOT/name).read_bytes()
            if name.endswith('.sh'):
                text=data.decode();end=text.index('\nfi\n')+4
                text='#!/bin/bash\n'+text[end:];data=text.encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(),expected,name)
    def test_disabled_host_methods_structurally_identical(self):
        guard=json.loads((FX/'legacy_guards.json').read_text())
        for key,expected in guard['functions'].items():
            file,name=key.split(':');tree=ast.parse((ROOT/file).read_text())
            methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name]
            method=methods[0]
            method.body=[n for n in method.body if not (isinstance(n,ast.If) and 'memory_rigor' in ast.unparse(n.test))]
            self.assertEqual(ast.dump(method,include_attributes=False),expected,key)
    def test_only_tv_enables(self):
        for p in (ROOT/'standalone').glob('tpms_cfg*.json'):
            enabled=json.loads(p.read_text()).get('memory_rigor',{}).get('enabled',False)
            self.assertEqual(enabled,p.name=='tpms_cfg_10.0-tv-kantsu2e.json',p.name)

if __name__=='__main__':unittest.main()

class LegacyComparisonTests(unittest.TestCase):
    def test_old_comparison_json_byte_identical(self):
        import sqlite3
        sys.path.insert(0,str(ROOT/'db'))
        from tpms_db import SCHEMA_SQL
        from tpms_db_queries import get_compare_detail_json
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;c.executescript(SCHEMA_SQL)
        c.executemany('insert into performance_data(job_name,build_number,test_name,metric_name,metric_value,metric_unit) values (?,?,?,?,?,?)', [('a',1,'Idle Memory Usage','IdleMemoryUsage',488,'MB'),('b',1,'Idle Memory Usage','IdleMemoryUsage',480,'MB'),('b',1,'MEMPS - only','MEMPS - only',123,'KB')])
        self.assertEqual(get_compare_detail_json(c,'a',1,'b',1),(FX/'legacy_compare.json').read_text())

class StrictInterventionParserTests(unittest.TestCase):
    def test_invalid_ion_input_does_not_emit_base_or_zero(self):
        with tempfile.TemporaryDirectory() as d:
            empty=Path(d)/'empty';empty.write_text('');out=Path(d)/'report.txt'
            command=[sys.executable,str(ROOT/'performance/script/memory_usage_test/host/get_used_memory.py'),'memory_usage_test','success',str(FX/'gcc_baseline/memps.txt'),'--strict','-s',str(empty),'-o',str(out)]
            result=subprocess.run(command,capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertFalse(out.exists())
