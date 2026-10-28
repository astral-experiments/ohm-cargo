"""Read one terminal H5 trial. Write a deterministic compressed JSON packet to stdout."""
import argparse
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
V1_WALL = 'd72ba2931a74d09d83d98e6c7d0829a6ad15fa4c756e8c99b6e1b569294e6917'
WALL = '9d2092c5482a2b63411f6d3357da7e0a95c732b89d1e6548a284bb1e0e286a8d'
NATIVE = 'ced75d44a721271455ea923ae40c0f38d693f7b559ad0ea0e40c4f9c42804039'
V1_GIT = '480e5f2dc1f69866145c98909ed0f327141e2928'
WALL_GIT = '3a7bba8da2347af0ee04f847ddc786e7be3783f2'
ADMISSION_GIT = 'bd7280e6aa38f26f48181d4c26a75f1508985203'
ADMISSION_SHA = '329818680f8d76f26cf15f6c4c5007c69001f6e85bd873c659a7bea283f6177e'
QA_GIT = 'd699d4cc9651cb91e84d1a012eadc9b53883f9ef'
QA_SHA = 'bfa3af0d64536cc2a5d59bb27a2f714a6dfd2b89a1943b6697c00e1a3d3c1beb'
V1_FAILURE = '356c561b3e5501c815caecd8c788439d0e52efc600e17555ef2cdf8a76092e80'
NATIVE_GIT = 'a75e5f17c07081cfcc9fabfcccd7a5022528641b'
SCHEMA = ('package_id','manifest_path','target','profile','features','filenames','executable')
SECRET = re.compile(r'(?i)openai[.](?:org|com|internal)|artifactory[.]|github[_]pat[_]|ghp[_][a-z0-9]{16}|https?://[^\s/]+@|(?:authorization|proxy-authorization):\s*(?:bearer|basic)|(?:token|password|secret|api_key)\s*[=:]\s*["\']?[^\s"\',]{10,}|-----BEGIN (?:\w+ )?PRIVATE KEY|(?:gh[pousr]_|github[_]pat[_]|sk-proj-)[a-zA-Z0-9_]{15,}|(?<![\w.-])[\w.-]+\.(?:openai\.(?:org|internal|com)|corp\.internal)(?=[^a-z]|$)')


def dig(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,separators=(',',':'),sort_keys=True).encode()


def file_sha(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src,'sha256').hexdigest()


def safe(raw):
    try:
        s=raw.decode()
    except UnicodeDecodeError:
        return None
    if '\0' in s or SECRET.search(s):
        return None
    return s


def gate(log):
    def code(role):
        p=log/(role+'.exit')
        if p.exists():
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
        if text is None:
            policy='private-text'
        else:
            policy='verbatim';bodies.setdefault(h,text)
    else:
        h=file_sha(path);n=path.stat().st_size;policy='digest-only'
    files[key]={'sha256':h,'bytes':n,'capture':policy}


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
    rows=[]
    for j in json.loads(path.read_bytes()):
        rows.append({k:j[k] for k in ('pid','kind','target','exit','raw')} |
                    {'argv_sha256':dig(canonical(j['argv'])),'exe_sha256':dig(j['exe'].encode())})
    return rows


def capture(base):
    log=base/'wall-launch-v2'
    status=gate(log) # No sampling or intermediate result read before a terminal exception or success.
    result=base/'early-scheduler-wall-rc17-v2';admit=base/'early-scheduler-wall-admission-v2.json'
    qa=base/'wall-qa-v1'/'qa.json';k=base/'wall-protocol-v2'
    files={};bodies={};slots={};problems={}
    def record(f,key,copy=True):
        add(files,bodies,f,key,include=copy)
    def existing(f,key,copy=True):
        if f.is_file():record(f,key,copy)
    for original,key in (('wall-launch-v1/binding.json','v1/binding.json'),('wall-launch-v1/admit.exit','v1/admit.exit'),('wall-launch-v1/admit.stdout','v1/admit.stdout'),('wall-launch-v1/admit.stderr','v1/admit.stderr'),('early-scheduler-wall-admission-v1.failure','v1/admission.failure'),('wall-protocol-v1/SHA256SUMS','v1/SHA256SUMS')):
        existing(base/original,key)
    for f in regular_files(k):
        record(f,'protocol/'+str(f.relative_to(k)),f.name in ('SHA256SUMS','wall-storage-preflight.json','wall-v1-failure-receipt.json'))
    assert files['protocol/SHA256SUMS']['sha256']==WALL
    for f in regular_files(log):
        record(f,'launcher/'+str(f.relative_to(log)),f.name!='launch.py')
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
    if result.is_dir():
        for f in sorted(result.iterdir()):
            if f.is_file():record(f,'result/'+f.name)
            elif f.is_dir():
                name=f.name
                assert re.fullmatch(r'[0-9]{2}-[12]-[BC]',name),name
                work=f/'private-state'
                slots[name]={'retained_state':work.is_dir()}
                if work.is_dir() and admit.is_file():
                    model=json.loads(admit.read_bytes())['native']
                    can=base/'ruff-evaluation-v2/canonical';inventory={}
                    for key in {*model['allowed'],*model['registry']}:
                        rel=Path(key).relative_to(can);assert rel.parts[0] in ('target','shared') and '..' not in rel.parts
                        path=work/rel
                        if path.is_file() and path.resolve().is_relative_to(work.resolve()):
                            inventory[key]={'bytes':path.stat().st_size,'sha256':file_sha(path)}
                        else:inventory[key]=None
                    slots[name]['terminal_retained_outputs']=inventory
                for path in sorted(f.iterdir()):
                    if path.is_file():
                        record(path,name+'/'+path.name)
                for sub in ('ordinary','unchanged'):
                    d=f/sub
                    if not d.is_dir():continue
                    for path in regular_files(d):
                        rel=str(path.relative_to(d));key=name+'/'+sub+'/'+rel
                        verbatim=(sub=='ordinary' or rel in ('command.json','products.json','e2e-list','registry-native.json','stderr'))
                        record(path,key,verbatim)
                    if sub=='unchanged':
                        for file,tag,fn in [('stdout','events',project_events),('physical.json','jobs',project_jobs)]:
                            if (d/file).is_file():
                                try:
                                    slots[name][tag]=fn(d/file)
                                except (ValueError,KeyError,TypeError,AttributeError) as err:
                                    problems[name+'/'+file]=type(err).__name__
    assert status!='complete' or not problems,problems
    return dict(schema=2,status=status,wall_git=WALL_GIT,native_git=NATIVE_GIT,native_manifest=NATIVE,qa_git=QA_GIT,first_wall_git=V1_GIT,admission_git=ADMISSION_GIT,
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
