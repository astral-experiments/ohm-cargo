"""Export already completed on-disk acquisitions. This program never invokes Cargo or a test binary."""
import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
CASES={
    'declared-enabled-v1':('qa','together',False,False,None),'declared-initial-v1':('qa','together',True,False,None),
    'staged-provider-v3':('qa','provider',False,False,None),'staged-provider-off-v3':('qa','provider',True,False,None),
    'staged-r17-v3':('17','provider',False,False,None),'staged-r17-off-v3':('17','provider',True,False,None),
    'staged-r18-v3':('18','provider',False,False,None),'staged-r19-v3':('19','provider',False,False,None),
    'staged-app-v3':('qa','app',False,False,None),
    'staged-only-native-v3':('qa','provider',False,True,None),'staged-only-native-off-v3':('qa','provider',True,True,None),
    'staged-clean-valid-v3':('qa','together',False,False,'valid'),'staged-clean-malformed-v3':('qa','together',False,False,'malformed'),
    'prebuilt-on-v2':('qa','external',False,False,None),'prebuilt-off-v2':('qa','external',True,False,None),
    'r17-v3':('17','external',False,False,None),'prebuilt-r18-v2':('18','external',False,False,None),'prebuilt-r19-v2':('19','external',False,False,None),
    'external-only-on-v3':('qa','external',False,True,None),'external-only-off-v3':('qa','external',True,True,None),
    'prebuilt-clean-valid-v2':('qa','external',False,False,'valid'),'prebuilt-clean-bad-v2':('qa','external',False,False,'malformed'),
}
def sha(b):return hashlib.sha256(b).hexdigest()
def file_sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(j):return (json.dumps(j,sort_keys=True,indent=1)+'\n').encode()
def inputs(runner):
    tree=ast.parse(runner)
    base=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='files')
    branch=next(n for n in tree.body if isinstance(n,ast.If) and isinstance(n.test,ast.Attribute) and n.test.attr=='external_provider')
    alt=next(ast.literal_eval(n.value) for n in branch.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Subscript))
    return base,alt
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path,help='parent of the 22 untouched native-* roots')
    p.add_argument('raw_runner',type=Path,help='preserved acquisition runner')
    p.add_argument('r18_provenance',type=Path,help='provenance.json from rc19-terminal-trait-ambiguity-release-hold')
    p.add_argument('dest',type=Path,help='receipt destination')
    args=p.parse_args();root=args.source.resolve();dest=args.dest
    dest.mkdir(exist_ok=True);members={};files={};cases={};subjects={};archive_bytes={};cached={}
    base,alt=inputs((HERE/'reproduce.py').read_bytes());assert inputs(args.raw_runner.read_bytes())==(base,alt)
    def commit(name,raw,portable):
        assert name not in files and isinstance(raw,bytes)
        files[name]={'bytes':len(raw),'sha256':sha(raw),'portable_bytes':len(portable),'portable_sha256':sha(portable)}
        members[name]=portable
    def digest_once(path):
        key=path.resolve()
        if key not in cached:cached[key]=file_sha(path)
        return cached[key]
    def product(path):
        return {'sha256':digest_once(path),'bytes':path.stat().st_size}
    r18=json.loads(args.r18_provenance.read_bytes())['official_18']
    for label,(image,kind,off,native_only,cold) in CASES.items():
        run=root/('native-'+label)
        sdk=(run/'rustup/toolchains/ohm').resolve(strict=True)
        replace=[(str(run),'/fixture'),(str(sdk),'/sdk'),(str(Path.home() / '.cargo/bin/cargo'),'/host-rustup/cargo'),
                 (str(Path.home() / '.cargo/bin'),'/host-rustup'),(str(Path.home()),'/user-home')]
        def project(raw):
            for old,new in replace:raw=raw.replace(old.encode(),new.encode())
            assert str(Path.home()).encode() not in raw
            return raw
        raw=(run/'result.json').read_bytes();res=json.loads(raw)
        commit(label+'/result.json',raw,project(raw))
        assert res['defaults_off'] is off
        shared=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin'
        required={'cargo':sdk/'bin/cargo','rustc':sdk/'bin/rustc','driver':next((sdk/'lib').glob('librustc_driver-*.so')),
                  'wild':shared/'wild-ld/ld.bfd'}
        if image=='17':
            required.update({'lld_dispatch':shared/'gcc-ld/ld.lld','rust_lld':shared/'rust-lld'})
        bound={k:product(v) for k,v in required.items()}
        assert all(res[k]==bound[k]['sha256'] for k in ('cargo','rustc'))
        if image not in subjects:
            rec={'images':bound}
            if image in ('17','19'):
                receipt=sdk.parent/'installed.json';installed=json.loads(receipt.read_bytes())
                archive=sdk.parent/('ohm-1.99.0-'+image+'-x86_64-unknown-linux-gnu.tar.gz')
                assert installed['release']=='ohm-1.99.0-'+image and digest_once(archive)==installed['archive']
                assert all(installed['images'][k]==bound[k]['sha256'] for k in ('cargo','rustc','driver','wild'))
                rec.update({'archive':product(archive),'install_receipt_sha256':file_sha(receipt),'tag':installed['release'],
                            'commits':{k:next(x.split(': ')[1] for x in installed['versions'][k].splitlines() if x.startswith('commit-hash:')) for k in ('cargo','rustc')}})
            elif image=='18':
                assert all(r18['images'][k]==bound[k]['sha256'] for k in ('cargo','rustc','driver','wild'))
                rec.update({'archive':{'sha256':r18['archive_sha256']},'install_receipt_sha256':file_sha(args.r18_provenance),
                            'tag':r18['tag'],'commits':{k:next(x.split(': ')[1] for x in r18['versions'][k].splitlines() if x.startswith('commit-hash:')) for k in ('cargo','rustc')}})
            else:
                rec.update({'commits':{'cargo':'34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31','rustc':'eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53'},'tag':'QA production Cargo and source-built stage1 rustc'})
            subjects[image]=rec
        assert subjects[image]['images']==bound
        case={'subject':image,'provider':kind,'defaults_off':off,'only_native_edit':native_only,'cold':cold,'staged_path_identity':{},'still_present_elf':{},'terminal_archives':{}}
        cases[label]=case
        phases=[x['phase'] for x in res['rows']]
        assert phases==(['empty'] if cold else ['initial','settled','declared-valid','repeat-valid','declared-malformed','repeat-malformed','restored'])
        for row in res['rows']:
            phase=row['phase'];test=run/phase
            for f,h in row['outputs'].items(): assert file_sha(test/f)==h
            main=base.copy()
            if kind=='external':main['provider/build.rs']=alt;del main['provider/state']
            else:main['provider/state']=row['state']+'\n'
            src_value=1 if native_only else row['lib']
            main['app/src/lib.rs']=f'pub fn value() -> i32 {{ middle::base() + {src_value} }}\n'
            assert {k:sha(v.encode()) for k,v in main.items()}==row['sources']
            if phase==phases[-1]:
                assert all((run/'project'/k).read_text()==v for k,v in main.items())
            cmd_paths={}
            for sub,path in [('test',test),('prepare',test/'prepare')]:
                if not path.exists():continue
                for filename in sorted(f.name for f in path.iterdir() if f.is_file()):
                    assert filename in ('exec.log','stdout','stderr','native.stdout','native.stderr')
                    data=(path/filename).read_bytes()
                    commit('/'.join((label,phase,sub,filename)),data,project(data))
                stdout=[json.loads(v) for v in (path/'stdout').read_bytes().splitlines() if v.startswith(b'{')]
                scripts=[x for x in stdout if x['reason']=='build-script-executed']
                assert len(scripts)==1,(label,phase,sub)
                paths=[scripts[0]['out_dir'],*scripts[0]['linked_paths']]
                cmd_paths[sub]=paths
                if sub=='test' and row['cargo']==0:
                    artifacts=[x for x in stdout if x.get('target',{}).get('name')=='probe' and x.get('executable')]
                    assert len(artifacts)==1
                    exe=Path(artifacts[0]['executable'])
                    if exe.is_file():case['still_present_elf'][project(str(exe).encode()).decode()]=product(exe)
            if 'prepare' in cmd_paths:
                assert cmd_paths['test']==cmd_paths['prepare']
                assert all(Path(x.removeprefix('native=')).is_dir() for x in cmd_paths['test'])
                ans=[sha(x.encode()) for x in cmd_paths['test']]
                resolved=[sha(os_path.encode()) for os_path in (str(Path(x.removeprefix('native=')).resolve()) for x in cmd_paths['test'])]
                case['staged_path_identity'][phase]={'original_sha256':ans,'resolved_sha256':resolved}
            if phase==phases[-1]:
                for role,src in zip(('early','fallback'),cmd_paths['test'][1:],strict=True):
                    name=Path(src.removeprefix('native='))/'libchoice.a'
                    if name.is_file():
                        b=name.read_bytes();key=sha(b)
                        archive_bytes[key]=b
                        case['terminal_archives'][role]={'sha256':key,'bytes':len(b)}
                    else:case['terminal_archives'][role]=None
        lock=(run/'project/Cargo.lock').read_bytes()
        commit(label+'/Cargo.lock',lock,lock)
    for key,b in archive_bytes.items():commit('native-inputs/'+key,b,b)
    with (dest/'streams.tar.gz').open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w') as archive:
        for name,data in sorted(members.items()):
            x=tarfile.TarInfo(name);x.size=len(data);x.mode=0o644;archive.addfile(x,io.BytesIO(data))
    host_tools={k:product(Path('/usr/bin')/k) for k in ('ar','cc','ld')};host_tools['rustup_proxy']=product(Path.home()/'.cargo/bin/cargo')
    report={'schema':1,'sha_algorithm':'sha256','cases':cases,'subjects':subjects,'host_tools':host_tools,'raw_runner':file_sha(args.raw_runner),
            'portable_runner':file_sha(HERE/'reproduce.py'),'original_streams':files}
    with (dest/'custody.json.gz').open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as gz:gz.write(dump(report))
    print(len(cases),'histories;',len(files),'original/portable file pairs;',len(archive_bytes),'distinct terminal archive payloads')
if __name__=='__main__':main()
