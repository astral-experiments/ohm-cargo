"""Read one terminal H5 trial. Write a deterministic compressed JSON packet to stdout."""
import argparse
import base64
import ast
import collections
import gzip
import hashlib
import json
import re
import socket
import sys
from pathlib import Path

H5 = 'charlie-ohm-c5-check-1025'
BASE = Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
WALL = 'fdec44bb8406ac845ddb1459377c9f92d3dac6bf06b925f6a685443f863a3e25'
WALL_GIT = 'f8ee28c60e872a090b4600f473b303738be05029'
WALL_B='18d39259d88610e634243199b707c5435a506d77'
WALL_B_SHA='2db9f4a735f6ebaab6f86c77e5643d6a99dd00c7691d62de2bb1e168720ce3c8'
BOOT='4de32538d02e25b5c8f75e58eea48c9b55fd0445'
BOOT_SHA='72fbc1e3b648cdd6a89ca117bf6ba8b4cb8a163e2610327389dbe5a97f58f159'
WALL_PARENT = '390db41469e8784dca0268c6317ea4b58b2e51c2'
WALL_PARENT_SHA = '9099beedd4c6a180c1c5747c077d1a45e1868e922dc594031d5ac4a292bfc9c4'
CONT_GIT = 'e53e5b70b667bc03a303c2ba2079c0d302b22746'
CONT_SRC = 'fa7ba5a8f256ce55d4e44eabd3a6ab777d0a786d5e45942bf1bea5e8781522f8'
STOPPED_GIT = 'f89d4913d40733b45227a41bb49d39cbb6d41015'
STOPPED_SHA = '5ff97dc91c067bf0e5da4a3e3097adc193ca71169aa1f0506fd05849719c284b'
NATIVE = 'ced75d44a721271455ea923ae40c0f38d693f7b559ad0ea0e40c4f9c42804039'
NATIVE_GIT = 'a75e5f17c07081cfcc9fabfcccd7a5022528641b'
QA_GIT = 'd699d4cc9651cb91e84d1a012eadc9b53883f9ef'
QA_SHA = 'bfa3af0d64536cc2a5d59bb27a2f714a6dfd2b89a1943b6697c00e1a3d3c1beb'
STOCK_GIT = '5b9490236f0557fb748a7b7e527e45452002904b'
STOCK_SRC = 'd116e7b75a81b1a5b8664248ab26425cc6ed4912abf7631e8cccdb4a14c7ead7'
SCHEMA = ('package_id','manifest_path','target','profile','features','filenames','executable')
SECRET = re.compile(r'(?i)openai[.](?:org|com|internal)|artifactory[.]|github[_]pat[_]|ghp[_][a-z0-9]{16}|https?://[^\s/]+@|(?:authorization|proxy-authorization):\s*(?:bearer|basic)|(?:token|password|secret|api_key)\s*[=:]\s*["\']?[^\s"\',]{10,}|-----BEGIN (?:\w+ )?PRIVATE KEY|(?:gh[pousr]_|github[_]pat[_]|sk-proj-)[a-zA-Z0-9_]{15,}|(?<![\w.-])[\w.-]+\.(?:openai\.(?:org|internal|com)|corp\.internal)(?=[^a-z]|$)')


def dig(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,separators=(',',':'),sort_keys=True).encode()


def file_sha(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src,'sha256').hexdigest()


def foreign_absolute(s):
    # Only conventional system data and explicitly public study roots may appear verbatim.
    # Native command arguments, registry JSON and trace lines are committed by digest regardless.
    roots=(str(BASE),'/home/dev-user/code/oss/ruff-ohm-combined-prs-20261028','/home/dev-user/.rustup/toolchains/ohm',
           '/usr','/lib','/lib64','/bin','/etc/ssl','/dev/null','/proc/self','/rustc')
    for path in re.findall(r"""(?:^|[\s"'(=])(/(?!/)[A-Za-z0-9_.-][^\s"'\\(){}\[\],;:]*)""",s):
        if '..' in Path(path).parts or not any(path==root or path.startswith(root+'/') for root in roots):
            return True
    for file_uri in re.findall(r'file://(/[^\s"\\#]+)',s):
        if not any(file_uri==root or file_uri.startswith(root+'/') for root in roots):return True
    return False

def safe(raw):
    try:
        s=raw.decode()
    except UnicodeDecodeError:
        return None
    if ('\0' in s or SECRET.search(s) or foreign_absolute(s)
        or re.search(r'/home/(?!dev-user/)[^/\s]+/|/Users/[^/\s]+/|/mnt/devbox-scratch/(?!dev-user/)[^/\s]+/',s)
        or re.search(r'/registry/(?:cache|index|src)/(?!index\.crates\.io-|github\.com-)[^/\s]+/',s)
        or any(not re.fullmatch(r'(?:github\.com|api\.github\.com|crates\.io|index\.crates\.io|static\.crates\.io|doc\.rust-lang\.org)',host,re.I)
               for host in re.findall(r'https?://([^/\s"<>]+)',s,re.I))):
        return None
    return s


def gate(log):
    def code(role):
        p=log/(role+'.exit')
        if p.exists():
            assert p.is_file() and not p.is_symlink(),p
            s=p.read_text()
            assert s==str(int(s)),p
            return int(s)
    a,b,c=(code(name) for name in ('admit','score','verify'))
    if a is not None and a!=0 and b is None and c is None:
        return 'admission-failed'
    if a==0 and b is not None and b!=0 and c is None:
        return 'score-failed'
    if a==b==0 and c is not None:
        return 'complete' if c==0 else 'verify-failed'
    raise ValueError('No terminal native and wall outcome. Leave the running trial unread.')


def add(files,bodies,path,key,*,include):
    assert key not in files and path.is_file() and not path.is_symlink(),(key,path)
    if include:
        b=path.read_bytes();h=dig(b);n=len(b);text=safe(b)
        # Exact H2 release bytes are carried both as JSON and base64. Inspect the enclosed
        # bytes explicitly before exporting them even when the outer JSON looks public.
        if key=='launcher/operator-release.json' and text is not None:
            try:
                data=json.loads(b);raw=base64.b64decode(data['h2_release_b64'],validate=True)
                if safe(raw) is None or json.loads(raw)!=data['h2_release']:text=None
            except (ValueError,KeyError,TypeError):text=None
        if text is None:
            policy='private-text'
        else:
            policy='verbatim';bodies.setdefault(h,text)
    else:
        h=file_sha(path);n=path.stat().st_size;policy='digest-only'
    files[key]={'sha256':h,'bytes':n,'capture':policy}
    if policy=='private-text' and (key.endswith('.err') or key.endswith('.failure') or key.endswith('/first-failure.txt')):
        # Wholly private lines remain on the host. Safe lines of the original traceback are useful on their own.
        lines=[]
        for line in b.splitlines(keepends=True):
            text=safe(line)
            lines.append({'text':text} if text is not None else {'withheld_sha256':dig(line),'bytes':len(line)})
        files[key]['public_traceback_lines']=lines


def regular_files(root):
    if not root.exists():
        return []
    return sorted(f for f in root.rglob('*') if f.is_file() and not f.is_symlink())


def project_events(path):
    rows={};other=[];invalid=[];last=None
    for number,line in enumerate(path.read_bytes().splitlines(),1):
        try:
            r=json.loads(line);last=r.get('reason')
            if last=='compiler-artifact':
                item=json.dumps({k:r[k] for k in SCHEMA},sort_keys=True)
                ident=dig(item.encode())
                value=[r['fresh'],r['package_id'].startswith('path+'),r['executable'],r['profile']['test']]
                if ident in rows:raise ValueError('duplicate canonical Cargo row')
                rows[ident]=value
            else:
                other.append({'reason':last,'sha256':dig(line),'success':r.get('success'),
                              'diagnostic':dig(canonical(r['message'])) if last=='compiler-message' else None})
        except (ValueError,KeyError,TypeError,AttributeError):
            invalid.append([number,dig(line)])
    return {'rows':rows,'other':other,'invalid':invalid,'last':last}


def project_jobs(path):
    # Verify the literal successful exec line and exit, then retain hashed operands only.
    jobs=[]
    fmt=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[0-9a-f]+|NULL).*?\)\s+= 0$')
    for record in json.loads(path.read_bytes()):
        pid=record['pid'];assert re.fullmatch(r'exec\.\d+',pid)
        trace=path.parent/'trace'/pid;lines=trace.read_bytes().splitlines()
        match,=[line for line in lines if dig(line)==record['raw']]
        m=fmt.match(match);assert m and ast.literal_eval(m[1].decode())==record['exe'] and ast.literal_eval(m[2].decode())==record['argv']
        code=re.fullmatch(rb'\+\+\+ exited with (\d+) \+\+\+',lines[-1]);assert code and int(code[1])==record['exit']
        jobs.append({k:record[k] for k in ('pid','kind','target','exit','raw')} |
                    {'argv_sha256':dig(canonical(record['argv'])),'exe_sha256':dig(record['exe'].encode()),'trace_sha256':file_sha(trace)})
    assert len(jobs)==len({r['pid'] for r in jobs});return jobs

def path_key(key):
    assert not Path(key).is_absolute() and '..' not in Path(key).parts
    return key if safe(key.encode()) is not None else 'private-path-sha256/'+dig(key.encode())

def physical_lineage(base,existing):
    old=base/'whole-wild-width-v1';new=base/'whole-wild-width-v2';deployed=base/'whole-wild-width-v2-protocol';parent=base/'wall-protocol-v3'
    for name in ('source/SHA256SUMS','registration.json','source/stopped-source-binding.json','exit'):
        existing(deployed/name,'continuation/'+name,True)
    for label,root in [('retained',old),('adopted',new)]:
        for name in ('registration.json','source/SHA256SUMS'):
            existing(root/name,label+'/'+name,True)
    previous=base/'wall-protocol-v3b';boot=base/'whole-wild-width-v2-bootstrap'
    assert all(not p.is_symlink() and p.resolve()==p.absolute() for p in (previous,boot,base/'wall-launch-v3b'))
    for f in regular_files(previous):existing(f,'parent-b-source/'+str(f.relative_to(previous)),f.name=='SHA256SUMS')
    existing(base/'wall-launch-v3b/binding.json','parent-b-launch/binding.json')
    for n in ('registration.json','exit','source/SHA256SUMS','source/startup-binding.json'):existing(boot/n,'bootstrap/'+n,True)
    for n in ('bootstrap-completion.json','continuation-failure.txt','source/verify.py'):existing(new/n,'stock/'+n,n=='bootstrap-completion.json')
    existing(deployed/'stderr','continuation/stderr',False)
    for f in regular_files(parent):existing(f,'parent-source/'+str(f.relative_to(parent)),f.name=='SHA256SUMS')
    existing(base/'wall-launch-v3/binding.json','parent-launch/binding.json')
    def identity(f):
        if not f.exists() or f.is_symlink():return None
        st=f.stat();return [st.st_dev,st.st_ino]
    files={}
    for label,root in [('retained',old),('adopted',new)]:
        regular=['failure.txt','exit','seed.json','source/worker.py','commands/seed-repeat1/products.json']
        for phase in ('failure-1','failure-2','seed-repeat1'):
            regular.append('commands/'+phase+'/physical.json')
            regular.extend(str(f.relative_to(root)) for f in sorted((root/'captures'/phase).glob('*/capture.json')) if f.parent.name.isdecimal())
        files[label]={}
        for rel in regular:
            f=root/rel;ino=identity(f)
            if ino is not None and f.resolve().is_relative_to(root.resolve()) and f.is_file():
                existing(f,label+'/raw/'+rel,False);files[label][rel]=ino
    return {'root_identities':[identity(old),identity(new)],'file_identities':files,
            'untouched':{'parent_result_absent':not (base/'early-scheduler-wall-rc17-v3').exists(),
                         'parent_admission_absent':not (base/'early-scheduler-wall-admission-v3.json').exists(),
                         'old_second_phase_absent':not (old/'commands/seed-repeat2').exists(),
                         'old_terminal_absent':not (old/'terminal.json').exists(),
                         'parent_a_failure_absent':not (base/'early-scheduler-wall-admission-v3.failure').exists(),'parent_b_pristine':not any((base/n).exists() for n in ('early-scheduler-wall-rc17-v3b','early-scheduler-wall-admission-v3b.json','early-scheduler-wall-admission-v3b.failure'))}}


def capture(base):
    log=base/'wall-launch-v3c'
    assert not log.is_symlink() and log.resolve()==base.resolve()/'wall-launch-v3c'
    status=gate(log) # No sampling or intermediate result read before a terminal exception or success.
    result=base/'early-scheduler-wall-rc17-v3c';admit=base/'early-scheduler-wall-admission-v3c.json'
    qa=base/'wall-qa-v1'/'qa.json';k=base/'wall-protocol-v3c'
    for root in (result,admit,qa.parent,k,base/'whole-wild-width-v2',base/'whole-wild-width-v1',base/'whole-wild-width-v2-protocol',base/'wall-protocol-v3',base/'wall-launch-v3',base/'wall-native-proofs',base/'protocol-v2',base/'protocol-v3'):
        assert not root.is_symlink() and root.resolve()==root.absolute()
    files={};bodies={};slots={};problems={}
    def record(f,key,copy=True):
        add(files,bodies,f,path_key(key),include=copy)
    def existing(f,key,copy=True):
        if f.is_file():record(f,key,copy)
    for f in regular_files(k):
        record(f,'protocol/'+str(f.relative_to(k)),f.name in ('SHA256SUMS','wall-storage-preflight.json','wall-v1-failure-receipt.json'))
    assert files['protocol/SHA256SUMS']['sha256']==WALL
    for f in regular_files(log):
        record(f,'launcher/'+str(f.relative_to(log)),f.name!='job.py' and not (status!='complete' and f.name=='verify.out'))
    for f,name in ((admit,'admission.json'),(admit.with_suffix('.failure'),'admission.failure'),(qa,'qa.json')):
        existing(f,name)
    if qa.is_file():
        q=json.loads(qa.read_bytes())
        for r in [*q.get('build',{}).values(),*q.get('tests',{}).values()]:
            f=(qa.parent/r['evidence']).resolve()
            assert f.is_relative_to(qa.parent.resolve()) and not (qa.parent/r['evidence']).is_symlink()
            key='qa/'+str(f.relative_to(qa.parent.resolve()))
            if f.is_file() and key not in files:record(f,key,False)
    for dirname,source in (('v2','protocol-v2'),('v3','protocol-v3')):
        for name in ('SHA256SUMS','registered.json','adopted.json','adopted-seed.json'):
            existing(base/source/name,dirname+'/'+name)
    for name in ('variants.json','frozen-native-guard.json'):
        existing(base/'wall-native-proofs'/name,'native/'+name)
    root=base/'whole-wild-width-v2'
    for file in ('registration.json','wall-view.json','terminal.json','source/SHA256SUMS','continuation-registration.json','tree-before-resume.json','physical-preservation.json'):
        existing(root/file,'stock/'+file,file in ('registration.json','continuation-registration.json','tree-before-resume.json','physical-preservation.json'))
    if (root/'wall-view.json').is_file():
        declared=json.loads((root/'wall-view.json').read_bytes())['independent_verification']
        name=Path(declared['file'])
        if not name.is_absolute() and '..' not in name.parts:
            actual=root/name
            if actual.resolve()==actual.absolute():existing(actual,'stock/independent.json',False)
        # A missing or changed file remains a terminal failure with its original evidence;
        # the offline verifier compares any physical digest with the published one.
    lineage=physical_lineage(base,existing)
    if result.is_dir():
        for f in sorted(result.iterdir()):
            assert not f.is_symlink()
            if f.is_file():record(f,'result/'+f.name,not (status!='complete' and f.name=='result.json'))
            elif f.is_dir():
                name=f.name
                assert re.fullmatch(r'[0-9]{2}-[12]-[BC]',name),name
                work=f/'private-state'
                slots[name]={'retained_state':work.is_dir()}
                if work.is_dir() and admit.is_file():
                    assert not work.is_symlink() and work.resolve()==work.absolute()
                    model=json.loads(admit.read_bytes())['native']
                    can=BASE/'ruff-evaluation-v2/canonical';inventory={}
                    for key in {*model['allowed'],*model['registry']}:
                        rel=Path(key).relative_to(can);assert rel.parts[0] in ('target','shared') and '..' not in rel.parts
                        path=work/rel
                        if path.is_file() and path.resolve().is_relative_to(work.resolve()):
                            inventory[path_key(str(rel))]={'bytes':path.stat().st_size,'sha256':file_sha(path)}
                        else:inventory[path_key(str(rel))]=None
                    slots[name]['terminal_retained_outputs']=inventory
                for path in sorted(f.iterdir()):
                    if path.is_file():
                        record(path,name+'/'+path.name)
                for sub in ('ordinary','unchanged'):
                    d=f/sub
                    if not d.is_dir():continue
                    assert not d.is_symlink() and d.resolve()==d.absolute()
                    for path in regular_files(d):
                        rel=str(path.relative_to(d));key=name+'/'+sub+'/'+rel
                        verbatim=(sub=='ordinary' or rel in ('command.json','products.json','e2e-list','registry-native.json','stderr'))
                        record(path,key,verbatim)
                    if sub=='unchanged':
                        for file,tag,fn in [('stdout','events',project_events),('physical.json','jobs',project_jobs)]:
                            if (d/file).is_file():
                                try:
                                    value=fn(d/file)
                                    if safe(canonical(value)) is None:raise ValueError('private projection')
                                    slots[name][tag]=value
                                except (AssertionError,ValueError,KeyError,TypeError,AttributeError,FileNotFoundError) as err:
                                    problems[name+'/'+file]=type(err).__name__
    assert status!='complete' or not problems,problems
    return dict(schema=5,lineage=lineage,status=status,host=H5,wall_git=WALL_GIT,native_git=NATIVE_GIT,native_manifest=NATIVE,qa_git=QA_GIT,
                files=files,bodies=bodies,slots=slots,projection_errors=problems,result_directory_present=result.is_dir())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=BASE)
    a=parser.parse_args()
    assert socket.gethostname()==H5 and a.base==BASE
    p=capture(a.base)
    encoded=canonical(p)
    assert safe(encoded) is not None, 'Private endpoint or credential pattern found in public projection'
    packed=gzip.compress(encoded,compresslevel=6,mtime=0)
    print('WALL_EXPORT_SHA256',dig(packed),len(packed),file=sys.stderr)
    sys.stdout.buffer.write(packed)
