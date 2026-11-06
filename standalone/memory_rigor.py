"""Opt-in memory measurement model. Pure parsing, policy, storage and comparison.

No device access on import. Values are kB (1024 bytes); missing is never zero.
"""
import hashlib
import json
import math
import re
import sqlite3
import statistics
from pathlib import Path

DEFAULTS = dict(enabled=False, boots=1, samples=1, interval_s=30,
                min_uptime_s=600, gate_interval_s=30, window=10,
                memory_range_fraction=0.01, cpu_max_percent=21, max_wait_s=1800,
                coverage_min=0.95, ion_shrink=False, expected_nevra='',
                enforce_version=False, command_timeout_s=120, capture_timeout_s=300,
                capture_policy='fixed_uptime', capture_uptime_s=1800,
                initial_gate=False, min_valid_samples_per_boot=3)
SYSTEM_FIELDS = ('MemTotal', 'MemAvailable', 'MemFree', 'Cached', 'Shmem', 'Slab',
                 'SReclaimable', 'SUnreclaim', 'PageTables', 'KernelStack', 'SwapTotal', 'SwapFree')
PROCESS_FIELDS = ('Pss', 'SwapPss', 'Private_Dirty')


def config(section=None):
    cfg = dict(DEFAULTS)
    supplied = section or {}
    unknown = set(supplied) - set(cfg)
    if unknown:
        raise ValueError('unknown memory_rigor options: ' + ','.join(sorted(unknown)))
    cfg.update(supplied)
    for key in ('enabled', 'ion_shrink', 'enforce_version', 'initial_gate'):
        if not isinstance(cfg[key], bool):
            raise ValueError(key + ' must be boolean')
    for key in ('boots', 'samples', 'window', 'min_valid_samples_per_boot'):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(key + ' must be a positive integer')
    for key in ('interval_s', 'gate_interval_s', 'max_wait_s', 'command_timeout_s', 'capture_timeout_s', 'capture_uptime_s'):
        if not math.isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError(key + ' must be positive')
    if not 0 <= cfg['cpu_max_percent'] <= 100 or not 0 < cfg['coverage_min'] <= 1:
        raise ValueError('invalid CPU/coverage threshold')
    if not 0 < cfg['memory_range_fraction'] < 1 or cfg['min_uptime_s'] < 0:
        raise ValueError('invalid gate threshold')
    if cfg['capture_policy'] not in ('fixed_uptime', 'gate'):
        raise ValueError('invalid capture_policy')
    return cfg


def gate_decision(rows, cfg, start_uptime):
    """Elapsed limit measured in target uptime, not host wall time.

    A timeout is a collection condition, not fabricated steady state. A missing
    probe breaks the consecutive window. CPU rows describe elapsed intervals.
    """
    if not rows:
        return {'status': 'waiting', 'reason': 'insufficient_samples'}
    last = rows[-1]
    if any(r['boot_id'] != last['boot_id'] for r in rows):
        return {'status': 'error', 'reason': 'boot_id_changed'}
    up = last['uptime']
    w = rows[-cfg['window']:]
    eligible = len(w) == cfg['window'] and all(r.get('valid', True) for r in w)
    eligible = eligible and all(0 < b['uptime']-a['uptime'] <= cfg['gate_interval_s']*2
                                for a,b in zip(w,w[1:]))
    details = {}
    steady = False
    if eligible:
        threshold = last['MemTotal'] * cfg['memory_range_fraction']
        av = max(r['MemAvailable'] for r in w)-min(r['MemAvailable'] for r in w)
        sw = max(r['SwapUsed'] for r in w)-min(r['SwapUsed'] for r in w)
        cpu = statistics.mean(r['cpu'] for r in w) if all(r.get('cpu') is not None for r in w) else None
        details = dict(mem_range_kB=av, swap_range_kB=sw, cpu_mean=cpu, threshold_kB=threshold,
                       memory_stable=av < threshold and sw < threshold, cpu_met=cpu is not None and cpu <= cfg['cpu_max_percent'])
        steady = up >= cfg['min_uptime_s'] and av < threshold and sw < threshold and cpu is not None and cpu <= cfg['cpu_max_percent']
    if steady:
        return dict(status='steady', reason='steady_criteria_met', uptime=up, **details)
    if up-start_uptime >= cfg['max_wait_s']:
        return dict(status='limit', reason='按上限采集', uptime=up, **details)
    return dict(status='waiting', reason='criteria_not_met' if eligible else 'insufficient_samples', **details)


def capture_decision(rows, cfg, start_uptime):
    decision = gate_decision(rows, cfg, start_uptime)
    if cfg['capture_policy'] == 'gate' or decision['status'] == 'error' or not rows:
        return decision
    up = rows[-1]['uptime']
    details = {k: v for k, v in decision.items() if k not in ('status', 'reason', 'uptime')}
    details.setdefault('memory_stable', False)
    details.setdefault('cpu_met', False)
    if up < cfg['capture_uptime_s']:
        return dict(status='waiting', reason='waiting_fixed_uptime', uptime=up, **details)
    return dict(status='fixed' if details['memory_stable'] else 'unstable',
                reason='fixed_uptime_reached' if details['memory_stable'] else '采集时内存未平稳',
                uptime=up, **details)


def parse_stat_fields(text):
    end = text.rfind(')')
    rest = text[end+2:].split()
    if end < 0 or len(rest) < 20:
        raise ValueError('invalid proc stat')
    return dict(ppid=int(rest[1]), flags=int(rest[6]), starttime=int(rest[19]))


def image_identity(text):
    import shlex
    values = {}
    for line in text.splitlines():
        if '=' not in line or line.startswith('#'): continue
        key, value = line.split('=', 1)
        tokens = shlex.split(value)
        values[key] = ' '.join(tokens)
    identity = {k: values[k] for k in ('ID', 'VERSION_ID', 'VERSION', 'BUILD_ID', 'BUILD_VERSION') if values.get(k)}
    if not identity or not any(k in identity for k in ('VERSION_ID', 'VERSION', 'BUILD_ID', 'BUILD_VERSION')):
        raise ValueError('os-release lacks version/build identity')
    return json.dumps(identity, ensure_ascii=False, sort_keys=True)


def method_info(run):
    if run is None:
        return dict(memory_method='legacy_300s', capture_policy='legacy_300s', capture_uptime_s=300)
    cfg = run['config']
    # Old rigor_v1 payloads had implicit gate collection, not fixed uptime.
    return dict(memory_method=run.get('memory_method', 'rigor_v1'),
                capture_policy=run.get('capture_policy', cfg.get('capture_policy', 'gate')),
                capture_uptime_s=run.get('capture_uptime_s', cfg.get('capture_uptime_s', 1800)))


def comparison_warnings(a, b):
    ma, mb = method_info(a), method_info(b)
    warnings = []
    if ma != mb:
        warnings.append('测量方法不同，数值不可直接比较：' + json.dumps([ma, mb], ensure_ascii=False))
    for label, run in (('A', a), ('B', b)):
        if not run: continue
        warnings.extend(label + ': ' + w for w in run.get('warnings', []))
        for g in run['gates']:
            if g['status'] in ('limit', 'unstable'):
                warnings.append(f"{label} 开机 {g['boot_index']}: " + g['reason'])
    if a and b and ma['capture_policy'] == mb['capture_policy'] == 'gate':
        if [g['status'] for g in a['gates'] if g['boot_index']>0] != [g['status'] for g in b['gates'] if g['boot_index']>0]:
            warnings.append('gate 模式两侧门控状态不同，不能视为相同稳态')
    return list(dict.fromkeys(warnings))


def parse_kb(text, required):
    values = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        name, raw = line.split(':', 1)
        if name not in required:
            continue
        match = re.fullmatch(r'\s*(\d+)\s+kB\s*', raw)
        if not match or name in values:
            raise ValueError('bad/multiple kB field: ' + name)
        values[name] = int(match[1])
    missing = set(required)-set(values)
    if missing:
        raise ValueError('missing fields: ' + ','.join(sorted(missing)))
    return values


def parse_smaps(text):
    """Accept a rollup OR archived full smaps; sum exact field names only."""
    sums = {k: 0 for k in PROCESS_FIELDS}
    counts = {k: 0 for k in PROCESS_FIELDS}
    for line in text.splitlines():
        key = line.split(':', 1)[0]
        if key in sums:
            sums[key] += parse_kb(line, [key])[key]
            counts[key] += 1
    if not all(counts.values()) or len(set(counts.values())) != 1:
        raise ValueError('missing/incomplete smaps fields')
    sums['PssSwapPss'] = sums['Pss']+sums['SwapPss']
    return sums


def parse_stat(text):
    # comm may contain spaces and closing parentheses: fields follow the last ).
    end = text.rfind(')')
    rest = text[end+2:].split()
    if end < 0 or len(rest) < 20:
        raise ValueError('invalid proc stat')
    return int(rest[19])  # field 22, rest begins at field 3


def parse_memps(text):
    lines = text.splitlines()
    if not lines:
        raise ValueError('empty memps')
    header = lines[0].split()
    needed = ('PID','COMMAND','PSS','3D','GEM(PSS)')
    if not all(k in header for k in needed):
        raise ValueError('missing memps columns')
    processes = []
    for line in lines[1:]:
        if line.startswith('==='):
            break
        parts = line.split()
        if len(parts) != len(header):
            raise ValueError('truncated memps row')
        row = dict(zip(header,parts))
        for k in header:
            if k != 'COMMAND':
                row[k] = int(row[k])
        processes.append(row)
    total = re.search(r'^TOTAL:\s*(.+)\n\s*([^\n]+)', text, re.M)
    idle = re.search(r'^Used \(Mem\+Swap\):\s*(\d+)\s+MB\s*\(\s*(\d+)\s+kB\s*\)', text, re.M)
    if not total or not idle or not processes:
        raise ValueError('missing memps totals/idle/processes')
    keys, vals = total[1].split(), total[2].split()
    if len(keys) != len(vals):
        raise ValueError('truncated TOTAL')
    totals = dict(zip(keys,map(int,vals)))
    if not all(k in totals for k in ('PSS','3D','GEM(ALLOC)')):
        raise ValueError('missing TOTAL fields')
    if any(totals[k] < 0 for k in ('PSS','3D','GEM(ALLOC)')):
        raise ValueError('negative TOTAL')
    return dict(processes=processes, totals=totals, idle_mb=int(idle[1]), idle_kb=int(idle[2]))


def cpu_counters(text):
    fields = next(l for l in text.splitlines() if l.startswith('cpu ')).split()[1:]
    nums = list(map(int,fields[:8])) # exclude guest/guest_nice already in user/nice
    if len(nums) < 5:
        raise ValueError('incomplete cpu counters')
    return sum(nums), nums[3]+nums[4]


def cpu_percent(before, after):
    total, idle = after[0]-before[0], after[1]-before[1]
    if total <= 0 or not 0 <= idle <= total:
        raise ValueError('CPU counter reset/invalid delta')
    return 100*(total-idle)/total


def read_item(directory, name, nonempty=True):
    """Every target operation has independent stdout/stderr/rc/time evidence."""
    p = Path(directory)/name
    start = float(Path(str(p)+'.start').read_text())
    end = float(Path(str(p)+'.end').read_text())
    if not math.isfinite(start) or not math.isfinite(end) or end < start:
        raise ValueError(name + ': invalid operation time')
    stderr = Path(str(p)+'.stderr').read_text(errors='replace')
    rc = int(p.with_suffix(p.suffix+'.rc').read_text().strip())
    if rc:
        err = p.with_suffix(p.suffix+'.stderr').read_text(errors='replace').strip()
        raise ValueError(f'{name}: rc={rc} {err}')
    data = p.read_bytes()
    if nonempty and not data.strip():
        raise ValueError(name + ': empty')
    return data.decode(errors='replace')


def parse_snapshot(directory, identity, cfg):
    p = Path(directory)
    errors, metrics, processes = [], {}, []
    result = dict(identity, metrics=metrics, processes=processes, errors=errors, valid=False,
                  coverage=0.0, inventory_complete=False, raw_path=str(p))
    def get(name, nonempty=True):
        return read_item(p,name,nonempty)
    try:
        sid = get('snapshot_id').strip()
        boot = get('boot_id').strip()
        if sid != identity['snapshot_id'] or boot != identity['boot_id'] or get('boot_id_end').strip()!=boot:
            raise ValueError('snapshot_id/boot_id mismatch')
        result['uptime'] = float(get('uptime').split()[0])
        result['end_uptime'] = float(get('uptime_end').split()[0])
        if result['end_uptime'] < result['uptime']:
            raise ValueError('uptime moved backwards')
    except (ValueError,OSError,IndexError) as e:
        errors.append(str(e))
    try:
        mem = parse_kb(get('meminfo.txt'), SYSTEM_FIELDS)
        if mem['SwapFree'] > mem['SwapTotal'] or max(mem['MemFree'], mem['MemAvailable']) > mem['MemTotal'] or mem['MemTotal'] <= 0:
            raise ValueError('inconsistent memory totals')
        metrics.update({'Rigor_'+k:v for k,v in mem.items()})
        metrics['Rigor_SwapUsed'] = mem['SwapTotal']-mem['SwapFree']
        # Explicit accounting basis, NOT physical RAM cost of compressed swap.
        metrics['Rigor_UsedMem'] = mem['MemTotal']-mem['MemAvailable']
        metrics['Rigor_AccountedUsed'] = mem['MemTotal']-mem['MemFree']+metrics['Rigor_SwapUsed']
        get('vmallocinfo.txt')
        get('swaps.txt')
        mp = parse_memps(get('memps.txt'))
        result['legacy'] = mp
        metrics.update(Rigor_Memps3D=mp['totals']['3D'], Rigor_MempsGEM=mp['totals']['GEM(ALLOC)'])
    except (ValueError,OSError,IndexError) as e:
        errors.append(str(e))
    try:
        devices = get('zram_devices',False).splitlines()
        occupied = 0
        for dev in devices:
            vals = list(map(int,get('zram/'+Path(dev).name).split()))
            if len(vals)<3 or any(v<0 for v in vals):
                raise ValueError('invalid zram mm_stat')
            occupied += vals[2] # mem_used_total, bytes (not orig_data_size)
        metrics['Rigor_ZramUsed'] = occupied/1024
    except (ValueError,OSError) as e:
        errors.append(str(e))
    try:
        pids = get('pids').split()
        if not pids or len(set(pids))!=len(pids) or not all(x.isdigit() for x in pids):
            raise ValueError('invalid process inventory')
        def vanished(name):
            marker = p/(name+'.errno')
            return marker.is_file() and marker.read_text().strip() in ('ENOENT', 'ESRCH')
        for pid in pids:
            proc = dict(pid=int(pid), valid=False, errors=[], classification='user')
            processes.append(proc)
            prefix = 'proc/'+pid+'/'
            try:
                try:
                    proc.update(parse_stat_fields(get(prefix+'stat')))
                except (ValueError, OSError):
                    if vanished(prefix+'stat'):
                        proc['classification']='exited'
                        proc['errors'].append('采集期间退出：首次 stat ENOENT/ESRCH')
                        continue
                    raise
                if proc['flags'] & 0x00200000:
                    proc['classification']='kernel'
                    continue
                # Preserve whatever identity is readable even for a dying process.
                for name in ('comm','exe'):
                    try: proc[name]=get(prefix+name).rstrip('\n')
                    except (ValueError,OSError): pass
                try:
                    endstat=parse_stat_fields(get(prefix+'stat_end'))
                except (ValueError,OSError):
                    if vanished(prefix+'stat_end'):
                        proc['classification']='exited'
                        proc['errors'].append('采集期间退出：末次 stat ENOENT/ESRCH')
                        continue
                    raise
                if proc['starttime'] != endstat['starttime']:
                    proc['classification']='exited'
                    proc['errors'].append('采集期间退出：starttime 改变（PID 复用）')
                    continue
                for name in ('comm','exe'):
                    if not proc.get(name): raise ValueError('missing '+name)
                proc['cmdline'] = get(prefix+'cmdline',False).replace('\x00',' ')
                proc['cgroup'] = get(prefix+'cgroup')
                match = re.search(r'^Threads:\s*(\d+)\s*$',get(prefix+'status'),re.M)
                if not match: raise ValueError('missing Threads')
                proc['threads'] = int(match[1])
                proc['metrics'] = parse_smaps(get(prefix+'smaps_rollup'))
                proc['valid'] = True
            except (ValueError,OSError,IndexError) as e:
                proc['errors'].append(str(e))
        eligible = [r for r in processes if r['classification']=='user']
        successful = [r for r in eligible if r['valid']]
        result['kernel_threads'] = sum(r['classification']=='kernel' for r in processes)
        result['exited_processes'] = [r for r in processes if r['classification']=='exited']
        result['coverage_denominator'] = len(eligible)
        result['coverage'] = len(successful)/len(eligible) if eligible else 0.0
        result['inventory_complete'] = bool(eligible) and len(successful)==len(eligible)
        if not eligible or result['coverage'] < cfg['coverage_min']:
            errors.append('smaps_rollup/identity coverage below threshold')
        for k in (*PROCESS_FIELDS,'PssSwapPss'):
            metrics['Rigor_Process'+k] = sum(r['metrics'][k] for r in successful) if successful else None
        # A partial sum is labelled by coverage; NEVER infer missing process=0.
    except (ValueError,OSError) as e:
        errors.append(str(e))
    result['items'] = []
    for rc_file in sorted(p.rglob('*.rc')):
        base = Path(str(rc_file)[:-3])
        try:
            result['items'].append(dict(name=str(base.relative_to(p)),rc=int(rc_file.read_text()),
              start_uptime=float(Path(str(base)+'.start').read_text()),end_uptime=float(Path(str(base)+'.end').read_text()),
              stderr=Path(str(base)+'.stderr').read_text(errors='replace'),
              stdout_sha256=hashlib.sha256(base.read_bytes()).hexdigest()))
        except (OSError,ValueError) as e:
            errors.append('incomplete command evidence: '+str(e))
    result['valid'] = not errors
    result['invalid_reason'] = '; '.join(errors)
    result.setdefault('uptime',None)
    return result


def aggregate(run):
    """No invalid values enter statistics; comparison also demands full counts."""
    buckets = {}
    for s in run['samples']:
        if not s['valid']: continue
        for metric,value in s['metrics'].items():
            if value is not None and math.isfinite(value):
                buckets.setdefault((s['phase'],metric if s['phase']=='base' else metric+'__'+s['phase']),{}).setdefault(s['boot_index'],[]).append(value)
    output=[]
    for (phase,metric), boots in sorted(buckets.items()):
        medians={str(b):statistics.median(v) for b,v in boots.items()}
        vals=list(medians.values())
        output.append(dict(phase=phase,metric=metric,boot_medians=medians,mean=statistics.mean(vals),
                           minimum=min(vals),maximum=max(vals),range=max(vals)-min(vals),
                           valid_samples=sum(map(len,boots.values()))))
    return output


SCHEMA = '''
CREATE TABLE IF NOT EXISTS memory_rigor_runs (
 run_id TEXT PRIMARY KEY, job_name TEXT, build_number INTEGER, image_id TEXT,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory_rigor_samples (
 run_id TEXT, image_id TEXT, build_number INTEGER, boot_index INTEGER, boot_id TEXT,
 sample_index INTEGER, snapshot_id TEXT, phase TEXT, metric TEXT, value REAL,
 unit TEXT, valid INTEGER, invalid_reason TEXT, uptime REAL, gate_status TEXT,
 PRIMARY KEY(run_id,snapshot_id,metric));
CREATE TABLE IF NOT EXISTS memory_rigor_gates (
 run_id TEXT, boot_index INTEGER, boot_id TEXT, status TEXT, uptime REAL,
 parameters TEXT, sequence TEXT, PRIMARY KEY(run_id,boot_index));
CREATE TABLE IF NOT EXISTS memory_rigor_processes (
 run_id TEXT, snapshot_id TEXT, pid INTEGER, comm TEXT, exe TEXT, starttime INTEGER,
 valid INTEGER, detail TEXT, PRIMARY KEY(run_id,snapshot_id,pid));
CREATE TABLE IF NOT EXISTS memory_rigor_aggregates (
 run_id TEXT, phase TEXT, metric TEXT, statistic TEXT, value REAL, unit TEXT,
 detail TEXT, PRIMARY KEY(run_id,phase,metric,statistic));
'''


def validate_run(run):
    if run.get('schema_version') != 1 or not run.get('run_id'):
        raise ValueError('invalid run schema')
    cfg=config(run['config'])
    seen=set(); boot_ids={}
    gates={g['boot_index']:g for g in run['gates']}
    for s in run['samples']:
        if s['snapshot_id'] in seen: raise ValueError('duplicate snapshot_id')
        seen.add(s['snapshot_id'])
        b=s['boot_index'];bid=s['boot_id']
        if b in boot_ids and boot_ids[b]!=bid: raise ValueError('mixed boot_id')
        boot_ids[b]=bid
        if s['run_id']!=run['run_id']: raise ValueError('mixed run_id')
        if s.get('valid'):
            gate=gates.get(b)
            if not gate or gate['boot_id']!=bid or gate['status']!=s['gate_status'] or gate['status'] not in ('steady','limit','fixed','unstable'):
                raise ValueError('sample/gate identity mismatch')
        if s.get('valid') and (s.get('errors') or any(v is None or not math.isfinite(v) for v in s['metrics'].values())):
            raise ValueError('invalid values labelled valid')
    if len(set(boot_ids.values()))!=len(boot_ids): raise ValueError('boot_id reused across boots')
    return cfg


def save_run(conn, run, job, build):
    validate_run(run)
    conn.executescript(SCHEMA)
    rid=run['run_id']; image=run['image_id']
    with conn:
        old=conn.execute('SELECT payload,job_name,build_number FROM memory_rigor_runs WHERE run_id=?',(rid,)).fetchone()
        payload=json.dumps(run,ensure_ascii=False,sort_keys=True)
        if old:
            if old[0]!=payload or old[1]!=job or old[2]!=build:
                raise ValueError('run_id already bound to different data/build')
            return
        conn.execute('INSERT INTO memory_rigor_runs VALUES (?,?,?,?,?)',(rid,job,build,image,payload))
        for s in run['samples']:
            for metric,value in (s['metrics'] or {'Rigor_Sample':None}).items():
                conn.execute('INSERT INTO memory_rigor_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (rid,image,build,s['boot_index'],s['boot_id'],s['sample_index'],s['snapshot_id'],s['phase'],metric if s['phase']=='base' else metric+'__'+s['phase'],
                   value if s['valid'] else None,'kB',int(s['valid']),s['invalid_reason'],s['uptime'],s['gate_status']))
            for p in s['processes']:
                conn.execute('INSERT INTO memory_rigor_processes VALUES (?,?,?,?,?,?,?,?)',
                  (rid,s['snapshot_id'],p['pid'],p.get('comm'),p.get('exe'),p.get('starttime'),int(p['valid']),json.dumps(p)))
        for g in run['gates']:
            conn.execute('INSERT INTO memory_rigor_gates VALUES (?,?,?,?,?,?,?)',
              (rid,g['boot_index'],g['boot_id'],g['status'],g.get('uptime'),json.dumps(run['config']),json.dumps(g)))
        for a in aggregate(run):
            for stat in ('mean','minimum','maximum','range'):
                conn.execute('INSERT INTO memory_rigor_aggregates VALUES (?,?,?,?,?,?,?)',
                  (rid,a['phase'],a['metric'],stat,a[stat],'kB',json.dumps(a)))
            for boot,val in a['boot_medians'].items():
                conn.execute('INSERT INTO memory_rigor_aggregates VALUES (?,?,?,?,?,?,?)',
                  (rid,a['phase'],a['metric'],'boot_'+boot+'_median',val,'kB',json.dumps(a)))


def run_quality(run):
    cfg=validate_run(run)
    base=[s for s in run['samples'] if s['phase']=='base']
    expected={(b,n) for b in range(1,cfg['boots']+1) for n in range(1,cfg['samples']+1)}
    counts=[]
    for b in range(1,cfg['boots']+1):
        samples=[s for s in base if s['boot_index']==b]
        good=sum(s['valid'] for s in samples)
        counts.append(dict(boot_index=b,valid=good,invalid=len(samples)-good,
                           missing=cfg['samples']-len(samples),
                           invalid_reasons=[dict(sample_index=s['sample_index'],reason=s['invalid_reason']) for s in samples if not s['valid']]))
    gates=[g for g in run['gates'] if g['boot_index']>0]
    gated=len(gates)==cfg['boots'] and {g['boot_index'] for g in gates}==set(range(1,cfg['boots']+1)) and all(g['status'] in ('steady','limit','fixed','unstable') for g in gates)
    pairs=[(s['boot_index'],s['sample_index']) for s in base]
    shape=len(set(pairs))==len(pairs) and set(pairs)<=expected
    warnings=list(run.get('warnings',[]))
    for b in range(1,cfg['boots']+1):
        samples=[s for s in base if s['boot_index']==b]
        identities={}
        for s in samples:
            for key in {(p.get('comm'),p.get('exe')) for p in s.get('exited_processes',[]) if p.get('comm') and p.get('exe')}:
                identities[key]=identities.get(key,0)+1
        for key,n in identities.items():
            if n>cfg['samples']/2:
                warnings.append(f'开机 {b}: {key[0]} {key[1]} 在多数样本中采集期间退出 ({n}/{cfg["samples"]})')
    return dict(valid=gated and shape and all(c['valid']>=cfg['min_valid_samples_per_boot'] for c in counts) and not run.get('errors'),
                samples=len(base),invalid_samples=sum(not s['valid'] for s in base),per_boot=counts,
                expected_samples=len(expected),method=method_info(run),gates=[{k:g.get(k) for k in ('boot_index','boot_id','status','reason','uptime','first_satisfied_uptime','memory_stable','cpu_met')} for g in run['gates']],
                capture_uptimes=[dict(boot_index=s['boot_index'],sample_index=s['sample_index'],uptime=s['uptime'],coverage=s.get('coverage'),kernel_threads=s.get('kernel_threads'),exited_processes=s.get('exited_processes',[]),inventory_complete=s.get('inventory_complete'),valid=s['valid'],invalid_reason=s.get('invalid_reason','')) for s in base],
                warnings=warnings,tools=run.get('tools',[]),cleanup=run.get('cleanup'),transfers=run.get('transfers',[]))


def compare_runs(a,b):
    qa,qb=run_quality(a),run_quality(b)
    out=dict(direction='A - B',quality_a=qa,quality_b=qb,metrics=[],process_groups=None,
             warnings=list(dict.fromkeys(comparison_warnings(a,b)+qa['warnings']+qb['warnings'])))
    if not qa['valid'] or not qb['valid']:
        out['conclusion']='存在无效或不足样本，不作结论'; return out
    aa={x['metric']:x for x in aggregate(a) if x['phase']=='base'}
    bb={x['metric']:x for x in aggregate(b) if x['phase']=='base'}
    for metric in sorted(aa.keys() | bb.keys()):
        x,y=aa.get(metric),bb.get(metric)
        delta=x['mean']-y['mean'] if x and y else None
        exceeds=delta is not None and abs(delta)>x['range'] and abs(delta)>y['range']
        out['metrics'].append(dict(metric=metric,delta_kB=delta,a=x,b=y,
          conclusion='差异超出波动' if exceeds else '在波动范围内，不作结论'))
    # Attribution uses the same central snapshot(s) as median process footprint.
    # This preserves additivity (independent per-process medians do not).
    def cohort(run):
        base=[s for s in run['samples'] if s['phase']=='base' and s['valid']]
        if not all(s.get('inventory_complete') for s in base): return None
        byboot={}
        for s in base: byboot.setdefault(s['boot_index'],[]).append(s)
        totals={}; instances={}; present={}
        for s in base:
            for p in s['processes']:
                if not p['valid'] or p.get('classification','user')!='user': continue
                key=(p['comm'],p['exe']);present.setdefault(key,set()).add(s['snapshot_id'])
        for samples in byboot.values():
            ordered=sorted(samples,key=lambda s:s['metrics']['Rigor_ProcessPssSwapPss'])
            n=len(ordered); central=[ordered[n//2]] if n%2 else ordered[n//2-1:n//2+1]
            for s in central:
                counts={}
                for p in s['processes']:
                    if not p['valid'] or p.get('classification','user')!='user': continue
                    key=(p['comm'],p['exe']);counts[key]=counts.get(key,0)+1
                    totals[key]=totals.get(key,0)+p['metrics']['PssSwapPss']/len(central)/len(byboot)
                for key,count in counts.items(): instances.setdefault(key,[]).append(count)
        return {k:dict(value=totals.get(k,0),instance_counts=instances.get(k,[]),
                        present_samples=len(v),total_samples=len(base)) for k,v in present.items()}
    ca,cb=cohort(a),cohort(b)
    if ca is None or cb is None:
        out['process_groups_reason']='进程元数据或 rollup 不完整；N/A 不补零';return out
    groups={}
    for group,keys in [('common',ca.keys()&cb.keys()),('only_a',ca.keys()-cb.keys()),('only_b',cb.keys()-ca.keys())]:
        rows=[dict(comm=k[0],exe=k[1],a=ca.get(k),b=cb.get(k)) for k in sorted(keys)]
        groups[group]=dict(rows=rows,sum_a_kB=sum(ca[k]['value'] for k in keys if k in ca) if group!='only_b' else None,
                          sum_b_kB=sum(cb[k]['value'] for k in keys if k in cb) if group!='only_a' else None)
    common=groups['common']['sum_a_kB']-groups['common']['sum_b_kB']
    unilateral=groups['only_a']['sum_a_kB']-groups['only_b']['sum_b_kB']
    if 'Rigor_UsedMem' not in aa or 'Rigor_UsedMem' not in bb:
        out['process_groups_reason']='旧严谨数据缺 Rigor_UsedMem，不用 AccountedUsed 替代拆分';return out
    accounted=aa['Rigor_UsedMem']['mean']-bb['Rigor_UsedMem']['mean']
    out['process_groups']=groups
    out['decomposition']=dict(common_process_delta_kB=common,one_side_contribution_kB=unilateral,
      system_residual_delta_kB=accounted-common-unilateral,used_mem_delta_kB=accounted,
      definition='Rigor_UsedMem = MemTotal - MemAvailable；系统残差为该口径减进程 Pss+SwapPss，非独立内核归因；Rigor_AccountedUsed 含文件缓存，仅作参考')
    return out


def load_run(conn,job,build):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='memory_rigor_runs'").fetchone(): return None
    rows=conn.execute('SELECT payload FROM memory_rigor_runs WHERE job_name=? AND build_number=? ORDER BY rowid DESC',(job,build)).fetchall()
    return json.loads(rows[0][0]) if rows else None
