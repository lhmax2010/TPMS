"""Small synthetic capture fixture, generated locally without /proc or a board."""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'standalone'))
from memory_rigor import config, parse_snapshot

MEMINFO=''.join(f'{k}: {v} kB\n' for k,v in dict(MemTotal=100000,MemAvailable=60000,MemFree=50000,Cached=10000,Shmem=100,Slab=2000,SReclaimable=1000,SUnreclaim=1000,PageTables=200,KernelStack=100,SwapTotal=10000,SwapFree=9000).items())
MEMPS='''PID PSS 3D GEM(PSS) COMMAND
1 1000 2 0 /sbin/init
2 2000 3 0 /usr/bin/app
====================
TOTAL: PSS 3D GEM(ALLOC)
3000 5 0
Used (Mem+Swap): 50 MB( 51200 kB)
'''
ROLLUP='Pss: 1000 kB\nSwapPss: 100 kB\nPrivate_Dirty: 500 kB\n'

def item(path,name,text,rc=0):
    p=Path(path)/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text)
    Path(str(p)+'.rc').write_text(str(rc))
    Path(str(p)+'.stderr').write_text('permission denied or process exited' if rc else '')
    Path(str(p)+'.start').write_text('600.00')
    Path(str(p)+'.end').write_text('601.00')


def stat(pid=1,start=100):
    return f'{pid} (name with ) spaces) S '+' '.join(['0']*18+[str(start)]+['0']*5)+'\n'


def capture(path,boot='boot1',sid='sid1'):
    for name,text in dict(boot_id=boot,boot_id_end=boot,uptime='600 1200',uptime_end='605 1210',snapshot_id=sid,
      **{'meminfo.txt':MEMINFO,'memps.txt':MEMPS,'vmallocinfo.txt':'0x1-0x2 4096 pages=1 vmalloc\n','swaps.txt':'Filename Type Size Used Priority\n'},
      pids='1\n2\n',zram_devices='/sys/block/zram0\n').items(): item(path,name,text)
    item(path,'zram/zram0','102400 51200 61440 0 0')
    for pid in (1,2):
        for name,text in dict(stat=stat(pid),stat_end=stat(pid),comm='app'+str(pid)+'\n',exe='/bin/app'+str(pid)+'\n',cmdline='app\x00--test\x00',status='Threads:\t2\n',cgroup='0::/system.slice/app\n',smaps_rollup=ROLLUP).items():
            item(path,f'proc/{pid}/{name}',text)
    return dict(run_id='run',boot_index=1,boot_id=boot,sample_index=1,snapshot_id=sid,phase='base',gate_status='steady')


def sample(boot=1,n=1,value=2000,valid=True,phase='base',rid='run'):
    proc=[dict(pid=1,comm='shared',exe='/bin/shared',starttime=100,threads=1,cgroup='x',cmdline='shared',valid=True,errors=[],metrics=dict(Pss=value-100,SwapPss=100,Private_Dirty=100,PssSwapPss=value))]
    return dict(run_id=rid,boot_index=boot,boot_id=f'boot{boot}',sample_index=n,snapshot_id=f'{rid}-{boot}-{n}-{phase}',phase=phase,
      gate_status='steady',metrics={'Rigor_ProcessPssSwapPss':value,'Rigor_AccountedUsed':value+500,'Rigor_UsedMem':value+300},processes=proc,
      valid=valid,invalid_reason='' if valid else 'missing',errors=[] if valid else ['missing'],uptime=600+n*30,inventory_complete=True)


def run(values=((1000,1100,1200),(1010,1110,1210)),rid='run'):
    cfg=config({'enabled':True,'boots':len(values),'samples':len(values[0])})
    return dict(schema_version=1,run_id=rid,image_id=rid,config=cfg,
      samples=[sample(b,n,v,rid=rid) for b,vs in enumerate(values,1) for n,v in enumerate(vs,1)],
      gates=[dict(boot_index=b,boot_id=f'boot{b}',status='steady',reason='steady_criteria_met',uptime=600,sequence=[]) for b in range(1,len(values)+1)],
      tools=[],warnings=[],errors=[])
