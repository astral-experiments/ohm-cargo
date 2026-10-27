"""Freeze the actual rejected preflight, both physical Ron records, and its selected rustc inputs."""
from pathlib import Path
import ast,fcntl,hashlib,json,os,re,subprocess
x=Path.home()/'.cache/ohm-233-position-qualified-20261027';p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');prev=x/'whole-ruff-observer-prefetch-fifo-v1'
assert (x/'prefetch-fifo-qualified/queue.rc').read_text().strip()=='1' and not list(prev.glob('timed-*')) and not list(prev.glob('audit-*'))
digest=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def stamp(f):
 s=f.stat();return [s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
get=lambda t:json.loads(t.read_bytes())
with (p/'native-measure.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 out={'zero_timed_or_audited':True,'v1_queue_rc':1,'v1_failure_sha256':digest(prev/'failure.txt'),'v1_queue_error_sha256':digest(x/'prefetch-fifo-qualified/queue-error.txt'),
      'source_index_sha256':get(prev/'subjects.json')['source_index'],'physical_stores':get(prev/'subjects.json')['physical_stores']}
 rows=[json.loads(l) for l in (prev/'anchor-test-V/stdout').read_bytes().splitlines()]
 rons=[r for r in rows if r.get('reason')=='compiler-artifact' and r['target']['name']=='ron']
 assert len(rons)==1 and rons[0]['fresh'] and all(r['fresh'] for r in rows if r.get('reason')=='compiler-artifact') and len([r for r in rows if r.get('reason')=='compiler-artifact'])==619
 out['active_cargo_artifact']=rons[0]
 md,=[Path(n) for n in rons[0]['filenames'] if n.endswith('.rmeta')]
 logical=p/'native-target';base=Path(out['physical_stores']['test'])/'target';m=base/md.relative_to(logical)
 proofs=[]
 for d in sorted(base.glob('debug/build/workspaces/*/*/ron/*/out/ron*.d')):
    enc,=d.parent.parent.glob('fingerprint/dep-lib-ron'); data=enc.read_bytes();dk=d.read_bytes()
    assert b'ohm-foreign-span-bytes' in dk and b'ohm-foreign-span-bytes' in data and data[-41:-37]==b'OBS1' and data[-33]==1
    calc=subprocess.check_output([x/'prefetch-fifo-qualified/subjects/verify-obs1'],input=data[:-32]).decode().strip();assert calc==data[-32:].hex()
    oms=list(d.parent.glob('libron*.rmeta'));assert len(oms)==1;other=oms[0]
    proofs.append({'role':'active' if other==m else 'passive','raw':str(logical/d.relative_to(base)),'encoded':str(logical/enc.relative_to(base)),
                   'metadata':str(logical/other.relative_to(base)),'metadata_sha256':digest(other),'metadata_stamp':stamp(other),'raw_sha256':digest(d),'encoded_sha256':digest(enc),
                   'raw_stamp':stamp(d),'encoded_stamp':stamp(enc),'OBS1_complete':True,'OBS1_blake3':calc})
 assert sorted(w['role'] for w in proofs)==['active','passive']
 out['proofs']=proofs;out['active_json_sha256']=digest(prev/'anchor-test-V/stdout')
 calls=[]
 for name in ['prepare-test-V','prepare-test-C']:
    d=prev/name;info=get(d/'receipt.json')
    for id,exe in info['processes']['executions']:
       if not exe.endswith('/rustc'):continue
       file=d/id
       for line in file.read_text().splitlines():
          if '"--crate-name", "ron"' not in line or not line.rstrip().endswith('= 0'):continue
          t=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert t
          av=[ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"',t[2])]
          outdir=av[av.index('--out-dir')+1];assert outdir==str(md.parent)
          calls.append({'phase':name,'pid':id,'image':exe,'out_dir':outdir,'argv':av,'raw_trace_sha256':digest(file)})
 assert calls and any(c['phase']=='prepare-test-V' for c in calls)
 out['active_rustc']=calls;out['preparation']={}
 for mode in ('build','test'):
    out['preparation'][mode]={}
    for arm in 'VC':
        rr=get(prev/f'prepare-{mode}-{arm}'/'receipt.json');out['preparation'][mode][arm]={'nunits':rr['units'],'dirty':len(rr['dirty']),'ns':rr['ns'],'work':rr['processes']['rustc'],'native_linkers':len(rr['processes']['linkers']),'receipt_sha256':digest(prev/f'prepare-{mode}-{arm}'/'receipt.json')}
    for name in ('build','test'):
       home=prev/('cargo-home-'+name);proofdir=home/'.ohm-registry-json-v1';allp=[f for f in sorted(proofdir.rglob('*')) if f.is_file()]
       h=hashlib.sha256()
       for f in allp:h.update(str(f.relative_to(proofdir)).encode()+b'\0'+f.read_bytes()+b'\0')
       out.setdefault('private_registry',{})[name]={'source':str(home),'files':len(allp),'payload_digest':h.hexdigest()}
 assert out['private_registry']['test']['files']>0 and out['private_registry']['build']['files']>0
 print(json.dumps(out,sort_keys=True,indent=2))
