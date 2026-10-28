"""Pure checks shared by native admission and the final raw-artifact reader."""
from collections import Counter
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
P = json.loads((HERE/'plan.json').read_bytes())
A = json.loads((HERE/'native-anchor.json').read_bytes())
FIELDS = ('package_id','manifest_path','target','profile','features','filenames','executable')
EMPTY_SHA = hashlib.sha256(b'').hexdigest()
WIDTH = re.compile(r'[a-f0-9]{64}')
REF = re.compile(r'[a-f0-9]{40}')


def read(path):
    return json.loads(path.read_bytes())


def save(path, data):
    with path.open('x') as stream:
        json.dump(data,stream,indent=2,sort_keys=True)
        stream.write('\n')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def dig(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def path_id(name):
    return hashlib.sha256(name.encode()).hexdigest()


def manifest(folder):
    data=(folder/'SHA256SUMS').read_text().splitlines()
    names=[]
    for line in data:
        value, name=line.split('  ',1)
        assert WIDTH.fullmatch(value) and Path(name).name==name and name!='SHA256SUMS'
        assert not (folder/name).is_symlink() and sha(folder/name)==value
        names.append(name)
    assert sorted(set(names))==sorted(names) and set(names)|{'SHA256SUMS'}=={p.name for p in folder.iterdir()}
    return sha(folder/'SHA256SUMS')


def ci(snapshot):
    checks=set(P['required_ci'])
    assert len(checks)==8 and len(snapshot)==2
    for number,arm in ((260,'C'),(261,'B')):
        row,=[r for r in snapshot if r['number']==number]
        assert row['head']==P['source_heads'][arm] and row['url']==f'https://github.com/astral-sh/ohm-cargo/pull/{number}'
        names=[r['name'] for r in row['checks']]
        assert len(names)==len(set(names)) and set(names)==checks|set(P['skip_ci'])
        for entry in row['checks']:
            assert entry['status']=='COMPLETED' and entry['conclusion']==('SUCCESS' if entry['name'] in checks else 'SKIPPED')
            assert re.fullmatch(r'https://github\.com/astral-sh/ohm-cargo/actions/runs/\d+/job/\d+',entry['detailsUrl'])
    return dig(snapshot)


def tree(folder):
    """Commit bytes, modes, ownership, nanosecond mtimes, symlinks, xattrs and internal hardlinks."""
    stream=hashlib.sha256();ids={};size=0;objects=0
    for f in sorted(folder.rglob('*')):
        st=f.lstat();name=str(f.relative_to(folder));key=(st.st_dev,st.st_ino)
        if stat.S_ISREG(st.st_mode):
            if key in ids:
                extra=['link',ids[key]]
            else:
                extra=sha(f);ids[key]=name;size+=st.st_size
        elif stat.S_ISDIR(st.st_mode):
            extra=None
        elif stat.S_ISLNK(st.st_mode):
            extra=['symlink',os.readlink(f)]
        else:
            raise ValueError('unsupported seed file type')
        attrs=[(k,hashlib.sha256(os.getxattr(f,k,follow_symlinks=False)).hexdigest())
               for k in sorted(os.listxattr(f,follow_symlinks=False))]
        row=[name,st.st_mode,st.st_uid,st.st_gid,st.st_mtime_ns,extra,attrs]
        stream.update(json.dumps(row,ensure_ascii=True,separators=(',',':')).encode()+b'\n');objects+=1
    return dict(digest=stream.hexdigest(),objects=objects,unique_file_bytes=size,unique_files=len(ids)),set(ids)


def events(data):
    raw=[json.loads(line) for line in data.splitlines()]
    assert raw[-1]=={'reason':'build-finished','success':True}
    assert {r['reason'] for r in raw}<={'compiler-artifact','build-script-executed','compiler-message','build-finished'}
    rows=[r for r in raw if r['reason']=='compiler-artifact'];assert rows
    typed=sorted(dig({k:r[k] for k in FIELDS}) for r in rows)
    assert len(set(typed))==len(typed)
    files=sorted({name for row in rows for name in row['filenames']})
    targets={r['target']['name']:r['executable'] for r in rows if 'test' in r['target']['kind'] and r['executable']}
    diag=sorted(dig(r['message']) for r in raw if r['reason']=='compiler-message')
    return dict(typed=typed,roster=dig(typed),units=len(typed),fresh=sum(r['fresh'] is True for r in rows),
                files=files,targets=targets,diag=diag)


def files(model, resolve):
    data={}
    for name in model['files']:
        f=resolve(name);assert f.is_file(),name
        with f.open('rb') as d: head=d.read(8)
        kind='elf' if head.startswith(b'\x7fELF') else 'archive' if head==b'!<arch>\n' else 'file'
        data[path_id(name)]={'kind':kind,'size':f.stat().st_size,'sha256':sha(f)}
    assert len(data)==len(model['files'])
    return data


def compare_model(model,fresh):
    ref=A['first']
    assert model['units']==ref['units']==11 and model['fresh']==fresh
    assert model['roster']==ref['roster'] and model['diag']==ref['diag']==[]
    assert set(model['targets'])==set(P['harnesses'])
    assert {k:path_id(v) for k,v in model['targets'].items()}=={k:v['file'] for k,v in ref['harness'].items()}


def validate_files(observed,reference):
    assert observed==reference,{'mismatch':sorted(k for k in set(observed)|set(reference) if observed.get(k)!=reference.get(k))}
    raw={k:v['sha256'] for k,v in observed.items()}
    assert len(raw)==P['declared_paths']==16 and dig(raw)==P['declared_raw_sha256']
    native={k:v['sha256'] for k,v in observed.items() if v['kind']=='elf'}
    assert len(native)==6 and native==A['first']['elf']
    for item in A['first']['harness'].values():
        assert native[item['file']]==item['sha256']


def listing(rec,model):
    out={}
    for name,path in sorted(model['targets'].items()):
        pre='list-'+name
        assert read(rec/(pre+'.status.json'))=={'exit':0,'argv':[path,'--list']}
        assert not (rec/(pre+'.stderr')).read_bytes()
        actual=sha(rec/(pre+'.stdout'))
        assert actual==A['first']['harness'][name]['listing']
        out[name]=actual
    assert set(out)==set(P['harnesses'])
    return out


def ordinary(rec, model):
    assert not (rec/'stdout').read_bytes()
    message=(rec/'stderr').read_text()
    assert 'Finished ' in message and not re.search(r'^\s*(?:Blocking|error|warning|Running)\b',message,re.M)
    paths=re.findall(r'^\s*Executable .+ \((.+)\)\s*$',message,re.M)
    assert sorted(Path(p).name for p in paths)==sorted(Path(p).name for p in model['targets'].values()),paths
    return {'stdout':sha(rec/'stdout'),'stderr':sha(rec/'stderr')}


EXEC=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[0-9a-f]+|NULL).*?\)\s+= 0$')
LINKERS={'ld','ld.bfd','ld.lld','rust-lld','wild','wild-ld','mold','ld.gold','collect2','gcc','cc','clang'}


def trace_inventory(folder, targets):
    """Read every successful kernel exec, including rustc probes and compiler/linker shims."""
    tools=[];whole={};cargo=0
    for f in sorted(folder.glob('exec.*')):
        whole[f.name]=sha(f);lines=f.read_bytes().splitlines()
        for line in lines:
            m=EXEC.fullmatch(line)
            if not m:
                assert not (line.startswith(b'execve(') and line.endswith(b'= 0'))
                continue
            path=ast.literal_eval(m[1].decode());name=Path(path).name
            argv=ast.literal_eval(m[2].decode())
            assert path not in targets and name not in {Path(t).name for t in targets}
            if name=='cargo':cargo+=1
            if name=='rustc' or name.startswith('rustc-') or name in LINKERS or name.startswith(('cc1','clang-')) or name.endswith(('-gcc','-ld','-ld.bfd')):
                tools.append({'basename':name,'argv':dig(argv),'raw':hashlib.sha256(line).hexdigest()})
    assert whole and cargo==2
    return dict(cargo_execs=cargo,tools=tools,trace_files=whole)


def grant_valid(registration,grant,admission_sha):
    assert set(grant)=={'action','admission_ref','admission_sha256','native_result_ref','wall_ref','wall_sha256'}
    assert REF.fullmatch(grant['admission_ref']) and len({grant['admission_ref'],registration['wall_ref'],P['native_source_ref'],P['native_result_ref']})==4
    assert grant==dict(action='score exact H2 24 fresh text-size pairs',admission_ref=grant['admission_ref'],
                       admission_sha256=admission_sha,native_result_ref=P['native_result_ref'],
                       wall_ref=registration['wall_ref'],wall_sha256=registration['wall_sha256'])
