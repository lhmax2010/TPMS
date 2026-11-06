"""Device orchestration for the opt-in memory_rigor configuration only."""
import hashlib
import re
import tarfile
import json
import logging
import shlex
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from memory_rigor import (config, gate_decision, parse_kb, cpu_counters, cpu_percent,
                          read_item, parse_snapshot, aggregate, validate_run, run_quality, capture_decision, image_identity)


def checked_script_command(script, args):
    # Never execute an empty result of command substitution. Quoting is shell-safe.
    return ('payload=$(cat '+shlex.quote(str(script))+'); read_rc=$?; '
            '[ "$read_rc" -eq 0 ] && [ -n "$payload" ] || exit 125; '
            'bash -c "$payload" memory_rigor '+ ' '.join(shlex.quote(str(a)) for a in args))


class MemoryRigorRunner:
    def __init__(self, owner):
        self.owner=owner
        self.device=owner._device
        self.cfg=config(owner.memory_rigor)
        self.root=Path(owner.host_result_path)/'memory_rigor'
        self.root.mkdir(parents=True,exist_ok=True)
        self.script=Path(owner.script_path)/'memory_usage_test/target/memory_rigor_capture.sh'
        self.remote_script=owner.target_exe_path+'/memory_rigor_capture.sh'
        self.run=None
        self.exported=set()
        self.remote_token=uuid.uuid4().hex
        self.transfers=[]

    def prepare(self):
        result=self.device.executeCmd_result('command -v tar >/dev/null && command -v sha256sum >/dev/null && mkdir -p '+shlex.quote(self.owner.target_exe_path),30)
        self.log_execution('prepare_directory',result)
        if result['returncode']!=0: raise RuntimeError('cannot prepare capture directory/tar/sha256sum')
        uid=self.device.executeCmd_result('id -u',30)
        self.log_execution('root_check',uid)
        if uid['returncode']!=0 or uid['stdout'].strip()!='0': raise RuntimeError('memory capture requires root')
        transfer=self.device.transfer_result('push',str(self.script),self.owner.target_exe_path,self.cfg['command_timeout_s'])
        self.log_execution('payload_push',transfer)
        if transfer['returncode']!=0: raise RuntimeError('capture payload push failed')
        # Payload hash verified through the result-returning transport, not push stdout.
        import hashlib
        r=self.device.executeCmd_result('sha256sum '+shlex.quote(self.remote_script),30)
        self.log_execution('payload_check',r)
        if r['returncode']!=0 or not r['stdout'].split() or r['stdout'].split()[0]!=hashlib.sha256(self.script.read_bytes()).hexdigest():
            raise RuntimeError('capture payload missing or hash mismatch')

    def log_execution(self,name,result):
        (self.root/'commands').mkdir(exist_ok=True)
        (self.root/'commands'/(name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))

    @property
    def remote_root(self):
        if not re.fullmatch(r'[0-9a-f]{32}', self.remote_token): raise ValueError('unsafe run token')
        return '/opt/usr/tpms/result/memory_rigor/'+self.remote_token

    def cleanup(self, remote=None):
        path=remote or self.remote_root
        if path!=self.remote_root and not path.startswith(self.remote_root+'/'):
            raise ValueError('unsafe cleanup path')
        targets=[path] if remote is None else [path,path+'.tar',path+'.tar.stdout',path+'.tar.stderr',path+'.tar.rc']
        command='rm -rf -- '+' '.join(map(shlex.quote,targets))+' && '+ ' && '.join('[ ! -e '+shlex.quote(t)+' ]' for t in targets)
        result=self.device.executeCmd_result(command,self.cfg['command_timeout_s'])
        self.log_execution('cleanup-'+Path(path).name,result)
        evidence=dict(path=path,verified=result['returncode']==0,returncode=result['returncode'])
        if remote is None and self.run is not None: self.run['cleanup']=evidence
        if not evidence['verified']: raise RuntimeError('run cleanup failed: '+path)
        return evidence

    def capture(self, mode, sid):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',sid): raise ValueError('unsafe snapshot_id')
        remote=self.remote_root+'/'+sid
        evidence=dict(snapshot_id=sid,mode=mode,board_seconds=None,pack_seconds=None,pull_seconds=None,file_count=None,verified=False)
        self.transfers.append(evidence)
        result=self.device.executeCmd_result(checked_script_command(self.remote_script,[mode,remote,sid]),
                    self.cfg['capture_timeout_s'] if mode=='snapshot' else self.cfg['command_timeout_s'])
        self.log_execution(sid,result)
        evidence['capture_rc']=result['returncode']
        if result['returncode']!=0 and not (mode=='snapshot' and result['returncode']==1):
            raise RuntimeError(f'{mode} command failed: {result}')
        match=re.search(r'^TPMS_ARCHIVE ([a-f0-9]{64}) ([0-9.]+) ([0-9.]+) ([0-9.]+) ([0-9.]+) ([0-9]+)\s*$',result['stdout'],re.M)
        if not match: raise RuntimeError('missing archive receipt')
        times=list(map(float,match.group(2,3,4,5)))
        if not times[0]<=times[1]<=times[2]<=times[3]: raise RuntimeError('invalid archive timing')
        evidence.update(board_seconds=times[1]-times[0],pack_seconds=times[3]-times[2],file_count=int(match[6]),sha256=match[1],pack_rc=0)
        local=self.root/sid;local.mkdir(exist_ok=False)
        archive=self.root/(sid+'.tar')
        began=time.monotonic()
        transfer=self.device.transfer_result('pull',remote+'.tar',str(archive),self.cfg['capture_timeout_s'])
        elapsed=time.monotonic()-began
        evidence.update(pull_seconds=elapsed,pull_rc=transfer['returncode'])
        self.log_execution(sid+'-pull',transfer)
        if transfer['returncode']!=0: raise RuntimeError('archive pull failed')
        h=hashlib.sha256()
        with archive.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
        if h.hexdigest()!=match[1]: raise RuntimeError('archive SHA-256 mismatch')
        with tarfile.open(archive,'r:') as tf:
            members=tf.getmembers()
            for m in members:
                if m.name.startswith('/') or '..' in Path(m.name).parts or not (m.isfile() or m.isdir()):
                    raise RuntimeError('unsafe archive member')
            if sum(m.isfile() for m in members)!=int(match[6]): raise RuntimeError('archive file count mismatch')
            for m in members:
                dest=local/m.name
                if m.isdir(): dest.mkdir(parents=True,exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with tf.extractfile(m) as src, dest.open('wb') as dst:
                        import shutil
                        shutil.copyfileobj(src,dst,1024*1024)
        evidence.update(archive_bytes=archive.stat().st_size,verified=True)
        evidence['cleanup']=self.cleanup(remote)
        (local/'transfer.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
        boot=read_item(local,'boot_id').strip()
        if boot!=read_item(local,'boot_id_end').strip(): raise RuntimeError('reboot during command')
        return local

    def gate(self, boot_index, gate_id=None):
        rows=[]; previous=None; start=None; boot=None; first_satisfied=None; first_memory=None; first_cpu=None
        token=gate_id or uuid.uuid4().hex
        while True:
            probe_started=time.monotonic()
            path=self.capture('probe',f'{token}-gate-{len(rows):04d}')
            current_boot=read_item(path,'boot_id').strip()
            uptime=float(read_item(path,'uptime').split()[0])
            if boot is None: boot=current_boot; start=uptime
            if current_boot!=boot: raise RuntimeError('boot_id changed in gate')
            mem=parse_kb(read_item(path,'meminfo.txt'),('MemTotal','MemAvailable','SwapTotal','SwapFree'))
            counters=cpu_counters(read_item(path,'cpu.txt'))
            row=dict(boot_id=boot,uptime=uptime,MemTotal=mem['MemTotal'],MemAvailable=mem['MemAvailable'],
                     SwapUsed=mem['SwapTotal']-mem['SwapFree'],cpu=cpu_percent(previous,counters) if previous else None)
            previous=counters; rows.append(row)
            criteria=gate_decision(rows,self.cfg,start)
            row.update(memory_stable=criteria.get('memory_stable',False),cpu_met=criteria.get('cpu_met',False))
            if row['memory_stable'] and first_memory is None: first_memory=uptime
            if row['cpu_met'] and first_cpu is None: first_cpu=uptime
            if criteria['status']=='steady' and first_satisfied is None: first_satisfied=uptime
            decision=capture_decision(rows,self.cfg,start)
            logging.info('memory gate boot=%s uptime=%.2f %s',boot,uptime,decision)
            gate=dict(decision,boot_index=boot_index,boot_id=boot,start_uptime=start,sequence=rows,parameters=self.cfg,first_satisfied_uptime=first_satisfied,first_memory_stable_uptime=first_memory,first_cpu_met_uptime=first_cpu)
            self.last_gate = gate
            (self.root/(token+'-gate.json')).write_text(json.dumps(gate,ensure_ascii=False,indent=2))
            if decision['status']!='waiting': return gate
            # Sleep only schedules probing. All policy times use board uptime.
            schedule_delay=max(0,self.cfg['gate_interval_s']-(time.monotonic()-probe_started))
            time.sleep(min(schedule_delay,max(0,(self.cfg['capture_uptime_s']-uptime if self.cfg['capture_policy']=='fixed_uptime' else self.cfg['max_wait_s']-(uptime-start)))))

    def standalone_gate(self):
        if not self.cfg['initial_gate']: return True
        self.remote_token=uuid.uuid4().hex
        ok=False
        try:
            self.prepare()
            gate=self.gate(0)
            self.initial_gate = gate
            (self.root/'initial_gate.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2))
            ok=gate['status'] in ('steady','limit','fixed','unstable')
        except Exception:
            logging.exception('memory initial gate failed')
        finally:
            try: self.initial_cleanup=self.cleanup()
            except Exception as e:
                self.initial_cleanup={'verified':False,'reason':str(e)}
                logging.exception('initial gate cleanup failed')
            print('已结束',datetime.now().astimezone().isoformat(),'状态 wait_for_stability')
        return ok and self.initial_cleanup['verified']

    def collect(self):
        rid=uuid.uuid4().hex
        self.remote_token=rid
        self.run=dict(schema_version=1,run_id=rid,image_id=None,requested_image_id=str(self.owner._snapshot_id),config=self.cfg,
                      memory_method='rigor_v2',capture_policy=self.cfg['capture_policy'],capture_uptime_s=self.cfg['capture_uptime_s'],
                      transfers=self.transfers,samples=[],gates=([self.initial_gate] if hasattr(self,'initial_gate') else []),tools=[],errors=[],warnings=[])
        try:
            self.prepare()
            if getattr(self,'initial_cleanup',{}).get('verified') is False: raise RuntimeError('initial gate cleanup failed')
            # Original installation path, including recorded latest fallback.
            self.owner._memory_tool_url=None
            self.owner._memory_tool_fallback_reason=None
            if not self.owner.install_package_from_repo('memps',allow_latest_fallback=True):
                raise RuntimeError('memps installation failed')
            for b in range(1,self.cfg['boots']+1):
                reboot_ok=self.device.reboot_device()
                self.log_execution(rid+f'-b{b}-reboot',dict(reboot_returned=reboot_ok,
                    target_rc=None,reason='reboot disconnects transport; verify new boot_id before accepting samples'))
                if not reboot_ok: raise RuntimeError('reboot failed')
                tools=self.capture('tools',rid+f'-b{b}-tools')
                nevra=read_item(tools,'nevra').strip(); sha=read_item(tools,'sha256').split()[0]
                fallback=getattr(self.owner,'_memory_tool_fallback_reason',None)
                if fallback:
                    warning='memps 回落 latest: '+fallback+'; URL='+str(self.owner._memory_tool_url)
                    if warning not in self.run['warnings']: self.run['warnings'].append(warning)
                tool=dict(boot_index=b,nevra=nevra,sha256=sha,download_url=self.owner._memory_tool_url,fallback_reason=fallback,
                          source_status='downloaded_this_run' if self.owner._memory_tool_url else 'preinstalled_url_unknown')
                osrelease=read_item(tools,'os-release')
                tool['os_release']=osrelease
                self.run['tools'].append(tool)
                image=image_identity(osrelease)
                if b>1 and self.run['image_id']!=image: raise RuntimeError('image changed across boots')
                self.run['image_id']=image
                if self.cfg['expected_nevra'] and nevra!=self.cfg['expected_nevra']:
                    warning='memps NEVRA mismatch: '+nevra+' expected '+self.cfg['expected_nevra']
                    self.run['warnings'].append(warning)
                    if self.cfg['enforce_version']: raise RuntimeError(warning)
                gate=self.gate(b,rid+f'-b{b}')
                self.run['gates'].append(gate)
                if gate['status'] not in ('steady','limit','fixed','unstable'): raise RuntimeError('gate failed')
                if any(g['boot_id']==gate['boot_id'] for g in self.run['gates'][:-1] if g['boot_index']>0):
                    raise RuntimeError('reboot did not change boot_id')
                if read_item(tools,'boot_id').strip()!=gate['boot_id']: raise RuntimeError('boot changed between tool check and gate')
                # Complete ALL baseline samples before any intervention.
                for phase in (('base','ion') if self.cfg['ion_shrink'] else ('base',)):
                    previous_end=None
                    if phase=='ion':
                        ip=self.capture('ion',rid+f'-b{b}-ion-intervention')
                        read_item(ip,'ion_write',False);read_item(ip,'ion_settle',False)
                    for n in range(1,self.cfg['samples']+1):
                        if previous_end is not None:
                            while True:
                                probe=self.capture('probe',rid+f'-b{b}-s{n}-{phase}-interval-'+uuid.uuid4().hex[:8])
                                if read_item(probe,'boot_id').strip()!=gate['boot_id']: raise RuntimeError('boot changed between samples')
                                now=float(read_item(probe,'uptime').split()[0])
                                remaining=previous_end+self.cfg['interval_s']-now
                                if remaining<=0: break
                                time.sleep(min(remaining,self.cfg['interval_s']))
                        sid=f'{rid}-b{b}-s{n}-{phase}'
                        identity=dict(run_id=rid,boot_index=b,boot_id=gate['boot_id'],sample_index=n,
                                      snapshot_id=sid,phase=phase,gate_status=gate['status'])
                        try:
                            path=self.capture('snapshot',sid)
                            sample=parse_snapshot(path,identity,self.cfg)
                        except Exception as e:
                            sample=dict(identity,valid=False,errors=[str(e)],invalid_reason=str(e),metrics={},processes=[],uptime=None,inventory_complete=False)
                        self.run['samples'].append(sample)
                        logging.info('memory snapshot %s valid=%s reason=%s',sid,sample['valid'],sample['invalid_reason'])
                        previous_end=sample.get('end_uptime',sample.get('uptime'))
                        self.persist()
        except Exception as e:
            logging.exception('memory rigorous run failed')
            self.run['errors'].append(str(e))
            if hasattr(self,'last_gate') and not any(g['boot_index']==self.last_gate['boot_index'] for g in self.run['gates']):
                failed=dict(self.last_gate,status='error',reason=str(e))
                self.run['gates'].append(failed)
        finally:
            try: self.cleanup()
            except Exception as e:
                self.run['errors'].append(str(e))
                logging.exception('run cleanup failed')
            self.persist()
            print('已结束',datetime.now().astimezone().isoformat(),'状态', '成功' if self.valid() else '失败')
        return self.valid()

    def valid(self):
        try:
            return self.run is not None and run_quality(self.run)['valid']
        except (ValueError,KeyError): return False

    def persist(self):
        if self.run is None: return
        self.run['aggregates']=aggregate(self.run)
        text=json.dumps(self.run,ensure_ascii=False,indent=2)
        path=Path(self.owner.host_result_path)/'memory_rigor.json'
        temp=path.with_suffix('.tmp');temp.write_text(text);temp.replace(path)
        try: quality=run_quality(self.run)
        except ValueError as e: quality={'valid':False,'reason':str(e)}
        (Path(self.owner.host_result_path)/'memory_rigor_report.json').write_text(json.dumps(dict(
            legacy_source='boot 1 / sample 1 / base only; no substitution',quality=quality,
            aggregates=self.run['aggregates'],tools=self.run['tools'],errors=self.run['errors']),ensure_ascii=False,indent=2))

    def export_legacy(self,kind):
        """Same legacy parsers/meaning, first base sample only, never failed zeros."""
        if not self.run: return False
        try: validate_run(self.run)
        except ValueError: return False
        first=next((s for s in self.run['samples'] if s['boot_index']==1 and s['sample_index']==1 and s['phase']=='base'),None)
        if not first or not first['valid']:
            warning='首开机首样本无效，旧内存指标不产生；严谨 run 按每开机有效样本下限判定'
            if warning not in self.run['warnings']: self.run['warnings'].append(warning)
            self.persist()
            return self.valid()
        # Re-parse and bind identity; file existence alone never authorizes reuse.
        checked=parse_snapshot(first['raw_path'],{k:first[k] for k in ('run_id','boot_index','boot_id','sample_index','snapshot_id','phase','gate_status')},self.cfg)
        if not checked['valid'] or checked['metrics']!=first['metrics']:
            first['valid']=False
            first['errors'].append('snapshot changed or failed validation on reuse')
            first['invalid_reason']='; '.join(first['errors'])
            self.persist()
            return False
        if kind in self.exported: return self.valid()
        names={'memory_usage_test':'get_used_memory.py','process_memory_usage_test':'get_process_memory_usage.py','memory_info_test':'get_memory_info.py'}
        base=Path(first['raw_path'])
        cmd=[str(Path(self.owner.script_path)/kind/'host'/names[kind]),kind,'success']
        if kind=='memory_info_test': cmd += [self.owner.profile_name,str(base/'meminfo.txt'),str(base/'vmallocinfo.txt'),str(base/'memps.txt')]
        else: cmd += [str(base/'memps.txt')]
        # Stage output: parser exceptions or zero failure rows never reach report.
        scratch=self.root/(kind+'.report')
        cmd += ['--strict','-o',str(scratch)]
        if scratch.exists(): scratch.unlink()
        try:
            result=subprocess.run(cmd,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=self.cfg['command_timeout_s'])
        except (OSError,subprocess.TimeoutExpired) as error:
            first['valid']=False
            first['errors'].append(kind+' parser execution failed: '+str(error))
            first['invalid_reason']='; '.join(first['errors'])
            self.log_execution(kind+'-parser',dict(returncode=None,error=str(error)))
            self.persist()
            return False
        self.log_execution(kind+'-parser',dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        if result.returncode!=0:
            first['valid']=False
            first['errors'].append(kind+' parser failed rc='+str(result.returncode))
            first['invalid_reason']='; '.join(first['errors'])
            self.persist()
            return False
        with open(self.owner.report_file,'a') as target: target.write(scratch.read_text())
        self.exported.add(kind)
        return self.valid()
