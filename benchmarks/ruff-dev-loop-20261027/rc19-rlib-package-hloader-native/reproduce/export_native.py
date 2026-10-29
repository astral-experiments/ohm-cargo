"""Select only publication-safe records from the native qualification; prints JSON."""
import collections,hashlib,json,sys
from pathlib import Path
from subprocess import check_output

def file_sha(path):
    with path.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def data_sha(s):return hashlib.sha256(s).hexdigest()
def read(p):return json.loads(p.read_bytes())
def export(root):
    reports=root/'reports';result={};raw={}
    def safe(name,data):
        path=reports/name
        raw[name]=file_sha(path)
        return read(path) if data is None else data
    def raw_only(name):
        p=reports/name;raw[name]=file_sha(p)
    result['setup']=safe('setup.json',None)
    result['training_and_edit']={}
    for p in sorted(reports.glob('*/product.json')):
        name=p.parent.name
        q=read(p)
        if name.startswith('ordinary-'):continue
        expected={'reported','top','unit','rmeta','old_candidate_sha','rmeta_sha','nlink','file_bytes','inode','device','target_rows','from_this_cargo'}
        assert set(q)==expected
        z={k:v for k,v in q.items()if k not in {'reported','top','unit','rmeta','inode','device'}}
        z['names']={k:Path(q[k]).name for k in ['top','unit','rmeta']}
        z['path_commitments']={k:data_sha(q[k].encode())for k in ['top','unit','rmeta']}
        typed=collections.Counter();roster=[];dirty=[]
        for line in (p.parent/'cargo.jsonl').read_text().splitlines():
            a=json.loads(line)
            if a.get('reason')!='compiler-artifact':continue
            role=(a['target']['name'],','.join(a['target']['kind']))
            typed[(role[1],a['fresh'])]+=1
            roster.append((role[0],role[1],sorted(data_sha(s.encode())for s in a['filenames'])))
            if not a['fresh']:dirty.append(role)
        z['artifact_roster_sha256']=data_sha(json.dumps(sorted(roster),sort_keys=True,separators=(',',':')).encode())
        z['declared_counts']={kind+' '+str(fresh):n for (kind,fresh),n in typed.items()}
        z['dirty']=sorted(dirty)
        q=safe(str(p.relative_to(reports)),z);raw_only(name+'/cargo.jsonl');raw_only(name+'/cargo.stderr')
        assert safe(name+'/exit.json',None)['exit']==0
        result['training_and_edit'][name]=q
    result['off_clock_cases']={}
    for p in sorted(reports.glob('proof-*/terminal.json')):
        name=p.parent.name
        trm=safe(str(p.relative_to(reports)),None);log=p.parent/'io.jsonl';rows=[json.loads(v)for v in log.read_bytes().splitlines()]
        assert [v['event']for v in rows]==['enrolled','open','rename','exit'] and rows[-1]==trm['event']
        raw_only(name+'/io.jsonl');raw_only(name+'/consumer/result.json');raw_only(name+'/consumer/compiler.stderr')
        trm['repeat_has_log']=(p.parent/'repeat.jsonl').exists();assert not trm['repeat_has_log']
        result['off_clock_cases'][name]=trm
    result['programs']={p.parent.name:safe(str(p.relative_to(reports)),None)for p in sorted(reports.glob('*/result.json'))}
    result['native_kernel_cases']=safe('native-guards-v2.json',None)
    result['original_open_fd_and_hardlink']=safe('stock-reverse-traced/old-handle.json',None)
    io=read(reports/'stock-reverse-traced/stock-io.json')
    result['stock_syscalls']=safe('stock-reverse-traced/stock-io.json',{k:v for k,v in io.items()if k not in ('open','first_raw_examples')})
    assert len(io['open'])==1 and 'O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC' in io['open'][0]
    result['stock_syscalls']['open_flags']='O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC'
    result['stock_span']=safe('stock-restored-timestamped/stock-span.json',None)
    result['archive_deltas']=safe('handoff/archive-deltas.json',None)
    result['custody']=safe('handoff/terminal.json',None)
    result['failed_preflights']={}
    for tag,needle,reason in [('stock-reverse','Invalid cross-device link','Holding a hard link across the private Btrfs subvolume failed with EXDEV before edited Cargo ran. The next attempt used an in-subvolume hardlink.'),
                     ('native-guards',"('observe-limited', [512, 0, -1, 27, 2, 0, 0])",'The initial regular-file logger added a second SIGXFSZ after an EFBIG. The corrected subject suppresses that logger when a size limit is set.')]:
        p=reports/('launch-'+tag);assert (p/'exit').read_text().strip()=='1'and needle in (p/'stderr').read_text()
        result['failed_preflights'][tag]={'exit':1,'stderr_sha256':file_sha(p/'stderr'),'reason':reason}
    result['software']={name:file_sha(root/name)for name in ('archive_probe-v2.so','archive_probe.so','archive_probe.c','qa_writer.c','native_guards.py','probe_qualification.py','reader.rs','cli_input.py','change.patch','stock_io.py','stock_span.py','handoff.py')}
    result['physical_raw_file_sha256']=dict(sorted(raw.items()))
    result['mounted_after_all_qualification']=bool(__import__('subprocess').run(['findmnt','-n','--mountpoint',root/'work'],stdout=__import__('subprocess').DEVNULL).returncode==0)
    assert not result['mounted_after_all_qualification']
    return result
if __name__=='__main__':
    print(json.dumps(export(Path(sys.argv[1])),sort_keys=True,indent=2))
