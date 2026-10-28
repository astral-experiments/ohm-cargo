"""Persist every real native command and product for one independently empty corrected Cargo/Rust history."""
from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,shutil,subprocess,sys,traceback
HERE=Path(__file__).resolve().parent;ORIG=Path.home()/'.cache/ohm-noquery-full-native-h4-20261028-v2/protocol';sys.path.insert(0,str(ORIG));import engine as q
q.ROOT=HERE;q.CASE=HERE/'states';q.RESULTS=HERE/'results'
sha=q.sha;dump=q.dump;load=q.load
FIX='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
RMINUS='52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955'
key='fixed-release-rust';phases=['cold','unchanged-1','unchanged-2','unchanged-3']
def outside():
    q.CASE.mkdir(mode=0o700);q.RESULTS.mkdir(mode=0o700)
    with q.LOCK.open('rb') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);assert shutil.disk_usage(HERE).free>45*2**30 and shutil.disk_usage(q.P).free>25*2**30
        assert q.git('rev-parse','HEAD').decode()=='93526150df078af7dd8fc4226cdcc469539d2001' and not q.git('status','--porcelain');st,d=q.init(key)
        assert sha(HERE/'fixed-cargo')==FIX and sha(ORIG/'SHA256SUMS')=='14d20e62691c4b124f52e106c66bc9926f3b92ecf6bf77ff017f264e1504c7e2'
        rv=load(ORIG/'subject-binding.json')['old_driver'];assert rv['sha256']==sha(rv['path'])==RMINUS
        env=q.env();env.pop('CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST');env.pop('CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST');env['CARGO_BUILD_JOBS']='8';env['CARGO_LOG']='cargo::compiler::fingerprint=info'
        opts=q.skeleton(st)
        for a,b in [(d,d),(st/'target',q.TARGET),(st/'build',q.BUILD),(st/'home',q.CH),(st/'rustup',q.P/'rustup')]:opts+=['--bind',str(a),str(b)]
        for a,b in [(HERE/'fixed-cargo',q.FROZEN/'bin/cargo'),(rv['path'],q.FROZEN/'lib'/q.SONAME)]:opts+=['--ro-bind',str(a),str(b)]
        for phase in phases:
            pr=subprocess.run([*opts,'--','taskset','-c','0-23','/usr/bin/python3','-IBu',str(HERE/'worker.py'),'inside',phase],cwd=q.WT,env=env,check=True)
        records={f:load(d/f/'record.json') for f in phases};dump(HERE/'complete.json',records)
def inside(phase):
    assert sha(q.FROZEN/'bin/cargo')==FIX and sha(q.FROZEN/'lib'/q.SONAME)==RMINUS and sha(q.FROZEN/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
    assert all(sha(q.FROZEN/n)==v for n,v in load(ORIG/'subject-binding.json')['sdk_files'].items())
    assert not {'RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST','CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST'}&os.environ.keys()
    d=q.RESULTS/key;folder=d/phase;folder.mkdir();(folder/'trace').mkdir();(folder/'ron').mkdir()
    if phase=='cold':assert not any(q.TARGET.iterdir()) and not any(q.BUILD.iterdir())
    cmd=['strace','-q','-ff','-ttt','-s','1048576','-e','trace=execve,execveat','-e','signal=SIGCHLD','-o',str(folder/'trace/exec'),*q.PLAN['command']]
    q.runwatched(cmd,folder,False);j=q.audit_json(folder/'stdout','test')
    rows=[x for l in (folder/'stdout').read_bytes().splitlines() if (x:=json.loads(l)).get('reason')=='compiler-artifact']
    assert len(rows)==619 and collections.Counter(bool(v['profile']['test']) for v in rows if v['executable'])=={True:84,False:18}
    ron,=[x for x in rows if x['target']['name']=='ron'];rlib,=[Path(n) for n in ron['filenames'] if n.endswith('.rlib')];rmeta,=[Path(n) for n in ron['filenames'] if n.endswith('.rmeta')]
    dep,=rlib.parent.glob('ron-*.d');fpd=rlib.parent.parent/'fingerprint';fp=fpd/'dep-lib-ron'
    copied={};mvals=[]
    for f in [rlib,rmeta,dep,*sorted(fpd.glob('*'))]:
        if f.is_file():
            to=folder/'ron'/f.name;shutil.copyfile(f,to);copied[f.name]=sha(to)
    members=subprocess.check_output(['ar','t',rlib],text=True).splitlines();assert len(set(members))==len(members)
    for name in members:
        b=subprocess.check_output(['ar','p',rlib,name]);mvals.append({'name':name,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)})
    encoded=fp.read_bytes();pdata=dep.read_bytes()
    proof={'raw_depfile':sha(dep),'raw_fingerprint':sha(fp),'foreign_span_marker':b'ohm-foreign-span-bytes' in pdata,'untrackable_span_marker':b'ohm-untrackable-foreign-span' in pdata,'optional_receipt':b'# ohm-observer-inputs-v1 ' in pdata,'checksum_records':len([l for l in pdata.splitlines() if l.startswith(b'# checksum:')]),'OBS1':encoded[-41:-37]==b'OBS1','complete':bool(encoded[-33]) if encoded[-41:-37]==b'OBS1' else None}
    rs={}
    for f in sorted((folder/'trace').glob('exec.*')):
        for l in f.read_bytes().splitlines():
            if b'"--crate-name", "ron"' not in l or not re.search(rb'\)\s+= 0$',l):continue
            m=re.search(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',l);assert m
            args=ast.literal_eval(m[2].decode());assert args[args.index('--crate-name')+1]=='ron' and Path(ast.literal_eval(m[1].decode())).samefile(q.FROZEN/'bin/rustc')
            rs[f.name]={'argv_digest':hashlib.sha256(json.dumps(args,separators=(',',':')).encode()).hexdigest(),'raw_line_sha256':hashlib.sha256(l).hexdigest(),'binary_dep_info':'-Zbinary-dep-depinfo' in args,'blake3':'-Zchecksum-hash-algorithm=blake3' in args}
    assert len(rs)==1
    snap={n:sha(n) for n in j['elf']};assert len(snap)==110;dump(folder/'native-elf.json',snap);dump(folder/'ron-members.json',mvals)
    try:
        physical=q.physical(folder,q.FROZEN,set(j['executables']));counts=physical['counts'];strict=True
        assert not physical['first_observer_capability_queries']
    except AssertionError:
        (folder/'physical-rejection').write_text(traceback.format_exc());counts=None;strict=False
    rec={'phase':phase,'elapsed_ns':None,'cargo_rc':0,'registry_reference':sha(d/'input-commitments.json'),'units':619,'declared_executables':102,'actual_elfs':110,'fresh':sum(x['fresh'] for x in rows),'diagnostics':j['message_sha256'],'roster':j['roster_sha256'],'actual_ron_args':rs,'strict_physical_roster':strict,'counts':counts,'ron_files_sha256':copied,'library':sha(rlib),'metadata':sha(rmeta),'ordered_members':mvals,'proof':proof,'reader':q.reader(j),'all_native_sha256':sha(folder/'native-elf.json'),'traces':{f.name:sha(f) for f in sorted((folder/'trace').glob('exec.*'))}}
    if phase!='cold':
        cold=load(d/'cold/record.json');assert all(rec[k]==cold[k] for k in ['units','declared_executables','actual_elfs','roster','diagnostics','reader'])
        raw_cold=load(d/'cold/native-elf.json');rec['changed_elf_names_from_cold']=[Path(n).name for n in sorted(snap) if snap[n]!=raw_cold[n]]
        rec['ron_equal_cold']=rec['library']==cold['library'] and rec['metadata']==cold['metadata']
    dump(folder/'record.json',rec);print(phase,rec['fresh'],counts,rec.get('ron_equal_cold'),flush=True)
try:
    if len(sys.argv)>1:inside(sys.argv[2])
    else:outside()
except BaseException:
    if len(sys.argv)==1:(HERE/'failure.txt').write_text(traceback.format_exc())
    raise
