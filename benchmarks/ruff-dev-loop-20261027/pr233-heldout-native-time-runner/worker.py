"""Measure only Cargo's process lifetime, then validate its complete artifacts, CLI, and immediate freshness."""
from pathlib import Path
import json, os, subprocess, sys, time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import ARENA, BOUND, QUAL, ORIGIN, SOURCE, load, dump, need, sha, capacity
from common import RUFF, FROZEN, SONAME, CARGO_HOME, env
from h5paths import release_output_roster
from witness import audit_json, as_digest, trusted_ancestors
from products import inputs_elf_key, oracle
from native_trace import trace_summary
from novel_state import verify_view

mode, arm, view, key, phase, name = sys.argv[1:]
need(mode in ('test','build') and arm in 'BC' and phase in ('settle','pre','timed','post'), 'worker')
d=ARENA/'receipts'/name
d.mkdir(parents=True)
reference=load(ARENA/'references.json')['/'.join((mode,arm,key))]
need(reference['source_view']==view and all(x['trusted'] for x in trusted_ancestors(CARGO_HOME)), 'isolated trusted registry')
verify_view(view,ORIGIN/'fixture')
cfg=env()
need(cfg['CARGO_BUILD_JOBS']=='8' and sorted(os.sched_getaffinity(0))==list(range(24)), 'jobs/affinity')
subject=BOUND['arms'][arm]
need(Path(subject['cargo']).samefile(FROZEN/'bin/cargo') and Path(subject['driver']).samefile(FROZEN/'lib'/SONAME), 'namespace subject mismatch')
cmd=[*SOURCE['primary_command' if mode=='build' else 'secondary_command'],'--message-format=json']

def cli(rows):
    ruff,={r['executable'] for r in rows if r.get('reason')=='compiler-artifact' and not r['profile']['test'] and r['target']['name']=='ruff' and r['target']['kind']==['bin'] and r.get('executable')}
    previous=oracle(ruff,False)
    spec=SOURCE['cli'];new=[]
    for source in [*spec['signed_sources'],spec['valid_indented_strings']]:
        q=subprocess.run([ruff,*spec['flags']],input=source.encode(),cwd=RUFF,env=cfg,capture_output=True)
        new.append({'input':source,'status':q.returncode,'stderr':q.stderr.decode(),'diagnostics':json.loads(q.stdout)})
    need(previous==reference['old_cli'] and new==reference['novel_cli'],'changed Ruff CLI output')
    return as_digest([previous,new])

def invoke(label,traced,fresh=False):
    path=d/label;path.mkdir()
    command=cmd if not traced else ['strace','-ff','-qq','-s','1048576','-e','trace=execve,execveat,prctl','-o',str(path/'exec'),*cmd]
    cap=capacity()
    with (path/'stdout').open('xb') as stdout,(path/'stderr').open('xb') as stderr:
        start=time.perf_counter_ns()
        process=subprocess.Popen(command,cwd=RUFF,env=cfg,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
        status=process.wait()
        stop=time.perf_counter_ns()
    record={'command':command if not traced else cmd,'traced':traced,'status':status,'stdout_sha256':sha(path/'stdout'),'stderr_sha256':sha(path/'stderr'),'before_free':cap,'after_free':capacity()}
    if phase=='timed' and not fresh:
        need(not traced, 'tracing the timed invocation')
        record['elapsed_ns']=stop-start
    dump(path/'invocation.json',record)
    stderr=(path/'stderr').read_text(errors='replace')
    need(status==0 and 'Blocking waiting' not in stderr,('failed command',name,label,status,stderr[-1250:]))
    rows=[json.loads(line) for line in (path/'stdout').read_bytes().splitlines() if line]
    j=audit_json(path/'stdout',mode)
    release=release_output_roster(rows,arm)
    checks={'units':j['units'],'roster':j['roster_sha256'],'release_roster':release,'messages':j['message_sha256'],'elf':sorted(inputs_elf_key(p) for p in j['elf']),'exes':len(j['executables'])}
    for k,v in checks.items():need(v==reference[k],('wrong Cargo output',name,label,k,v,reference[k]))
    work=trace_summary(path,j['executables']) if traced else None
    empty={'jobs':[],'native':{'wild':0,'cc':0,'collect2':0}}
    if fresh:need(not j['dirty'] and work==empty,('native work on immediate',name,work,j['dirty']))
    elif phase!='settle':
        need(j['dirty']==reference['dirty'],('changed dirty identities',name,j['dirty'],reference['dirty']))
        if traced:need(work==reference['native'],('wrong real native work',name,work,reference['native']))
    record.update(dirty=j['dirty'],native=work,structure=as_digest(checks),cli=cli(rows),unit_count=j['units'],elf_count=len(j['elf']),exe_count=len(j['executables']))
    dump(path/'receipt.json',record)
    return record

first=invoke('first',phase!='timed')
if phase=='settle':
    dump(d/'witness.json',dict(first=first,source_view=view,reference=reference['original_receipt']))
else:
    after=invoke('immediate',True,True)
    need(first['structure']==after['structure'] and first['cli']==after['cli'],'immediate changed products/CLI')
    dump(d/'witness.json',dict(first=first,immediate=after,source_view=view,reference=reference['original_receipt']))
