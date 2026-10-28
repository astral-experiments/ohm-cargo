"""Build a portable diagnostic record. Full unsanitized commands and ELF products stay on H7."""
import hashlib,json,os,shutil,sys
from pathlib import Path
p=Path(sys.argv[1]);dest=Path(sys.argv[2]);dest.mkdir()
sha=lambda v:hashlib.sha256(v).hexdigest()
read=lambda f:json.loads(f.read_bytes())
def dump(out,x):out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def copy(f,x):x.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,x)
def roll(arm):
    c=arm['caller'];return {k:arm[k] for k in ['stage','zip','typed','outputs']}|{'caller_sha':c['sha256'],'caller_bytes':c['bytes'],'caller_binary':c['binary'],'search_dirs':c['search_dirs'],'reader_archive_hashes':c['externs']}
for root in ('ir-children-v2','history-v1','cargo-grind-v2'):
    w=p/root;assert (w/'complete.json').is_file()
    copy(w/'complete.json',dest/root/'complete.json')
    for s in sorted((w/'rows').iterdir()):
        d=dest/root/s.name; record={}
        for typ in ('edited-products','settled-products'):
            f=s/typ/'verified.json';a=read(f);record[typ]=roll(a)
            record[typ]['verified_sha']=sha(f.read_bytes())
            # Consumer extern entries can contain canonical benchmark pathnames. Their raw proof
            # stays in the private receipt; the exported record retains exact library filenames.
            record[typ]['reader_archive_hashes']={k:Path(v).name for k,v in a['caller']['externs'].items()}
        for typ in ('counts.json','supervisor.json'):
            f=s/'edit'/typ
            if f.exists():copy(f,d/typ)
        for f in sorted((s/'edit').glob('*.count')):copy(f,d/f.name)
        for f in sorted((s/'edit').glob('*.args')):
            aa=f.read_bytes();args=aa.rstrip(b'\0').split(b'\0')
            record.setdefault('argv_sha256',{})[f.name]={'sha256':sha(aa),'argc':len(args),'crate':os.fsdecode(args[args.index(b'--crate-name')+1]) if b'--crate-name' in args else None}
        if (s/'repeat-jobs.json').exists():record['repeated_commands']=read(s/'repeat-jobs.json')
        if (s/'retained-proofs/files.json').exists():record['retained_proof_files']=read(s/'retained-proofs/files.json')
        dump(d/'native.json',record)
rows=[]
for f in sorted((p/'observations').glob('*/*/life.json')):
    obs=read(f);r=[]
    for q in obs['records']:
        args=q['argv'];name=Path(q['exe']).name;k=args[args.index('--crate-name')+1] if '--crate-name' in args else None
        r.append({**{n:q[n] for n in ('pid','ppid','first_ns','last_ns','utime_ticks','stime_ticks','cutime_ticks','cstime_ticks','io')},'exa':name,'crate':k,'argc':len(args),'argv_sha256':sha(b'\0'.join(os.fsencode(t) for t in args)+b'\0')})
    rows.append({'slot':str(f.parent.relative_to(p/'observations')),'hz':obs['hz'],'unscored_elapsed_ns':obs['elapsed'],'child_affinity':obs['child_cpus'],'sample_affinity':obs['monitor_cpus'],'raw_sha256':sha(f.read_bytes()),'processes':r})
dump(dest/'sampled-resources.json',rows)
elf=read(p/'buildscript-elf.json');dump(dest/'zip-builder.json',{k:v['elf'] for k,v in elf.items()})
plain=read(p/'unspaced-native-v1/complete.json');ur={}
for image,rows in plain.items():
    ur[image]=[{k:r[k] for k in ('step','stage','source','units','dirty','jobs','wild','outputs','zip','roster')}|{'caller_sha':r['caller']['sha256'],'caller_bytes':r['caller']['bytes'],'caller_binary':r['caller']['binary']} for r in rows]
dump(dest/'unspaced.json',ur)
copy(p/'ir-v1/rows/01-B/edit/stderr',dest/'rejected-all-process.stderr')
dump(dest/'rejected-all-process.json',{'native_result':'Cargo supervisor SIGSEGV under nested DynamoRIO','accepted':False,'release_measurements':0,'final_partial_counters':[{'name':f.name,'sha256':sha(f.read_bytes())} for f in sorted((p/'ir-v1/rows/01-B/edit').glob('*.count'))]})
for f in ('ssl-native-control/verified.json','cargo-grind-v2/function-summary/functions.json'):
    if (p/f).is_file():copy(p/f,dest/f)
partial=p/'cargo-grind-v1/rows/01-B/edit'
failedlog,=list(partial.glob('valgrind.*'));copy(failedlog,dest/'rejected-cargo-startup.log')
dump(dest/'rejected-cargo-startup.json',{'exit':133,'accepted':False,'source':'libc setenv startup in openssl_probe','counter_bytes':sum(f.stat().st_size for f in partial.glob('callgrind.*'))})
native=p.parent/'member-build-matched-protocol-v1';copy(native/'plan.json',dest/'native-design.json')
for f in (p/'scripts').glob('*'):
    if f.is_file() and f.name not in ('pack.py',):copy(f,dest/'workers'/f.name)
for f in (p/'tools-v1/calibration-v2/dispatch.c',p/'software-counters/callgrind/call-dispatch.c'):
    copy(f,dest/'workers'/('call-dispatch.c' if 'call-dispatch' in f.name else 'first-dispatch.c'))
dump(dest/'tools.json',{'drrun':sha((p/'tools-v1/sdk/bin64/drrun').read_bytes()),'dr_runtime':sha((p/'tools-v1/sdk/lib64/release/libdynamorio.so').read_bytes()),'dr_client':sha((p/'tools-v1/client/libpidcounter.so').read_bytes()),'callgrind':sha((p/'software-counters/callgrind/usr/libexec/valgrind/callgrind-amd64-linux').read_bytes()),'child_dispatch':sha((p/'tools-v1/children-v2/dispatch.so').read_bytes()),'cargo_dispatch':sha((p/'software-counters/callgrind/call-dispatch.so').read_bytes())})
if (p/'zip-cost-v1/complete.json').is_file():copy(p/'zip-cost-v1/complete.json',dest/'isolated-real-zip.json')
