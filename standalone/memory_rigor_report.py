#!/usr/bin/env python3
"""Offline report from saved run JSONs or the normal TPMS database. No device I/O."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from memory_rigor import compare_runs, load_run, run_quality, aggregate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-a',type=Path)
    parser.add_argument('--run-b',type=Path)
    parser.add_argument('--db',type=Path)
    parser.add_argument('--job-a');parser.add_argument('--build-a',type=int)
    parser.add_argument('--job-b');parser.add_argument('--build-b',type=int)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    state='失败'
    try:
        print('读取内存样本报告',flush=True)
        if args.db:
            with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True) as c:
                a=load_run(c,args.job_a,args.build_a)
                b=load_run(c,args.job_b,args.build_b) if args.job_b else None
        else:
            a=json.loads(args.run_a.read_text())
            b=json.loads(args.run_b.read_text()) if args.run_b else None
        if not a: raise ValueError('run A not found')
        report=compare_runs(a,b) if b else dict(quality=run_quality(a),aggregates=aggregate(a),tools=a['tools'])
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        state='成功';return 0
    except Exception as e:
        print(str(e),file=sys.stderr);return 1
    finally:
        print('已结束',datetime.now().astimezone().isoformat(),'状态',state)

if __name__=='__main__': sys.exit(main())
