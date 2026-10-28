"""Record the release compiler's real Unicode generator dev loop and native outputs."""
from pathlib import Path
import collections, fcntl, json, os, re, shutil, subprocess, sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from basic import *
import run_data as trace
u=json.loads((q/'ops/unicode-plan.json').read_bytes());root=q/'unicode-lifetime-v1';root.mkdir()
out=ram/'unicode-readers';out.mkdir()
objects=root/'raw';objects.mkdir()
assert sha(q/'ops/unicode.patch')==u['patch'] and sha(q/'ops/unicode-reader.rs')==u['caller']
def keep(f):
    z=sha(f); d=objects/z
    if not d.exists():shutil.copyfile(f,d);assert sha(d)==z
    return {'bytes':f.stat().st_size,'sha':z,'basename':f.name}
def ar(f):
    data=f.read_bytes();assert data.startswith(b'!<arch>\n');i=8;nms=b'';result=[]
    while i<len(data):
        hd=data[i:i+60];assert hd[58:60]==b'\x60\n';n=int(hd[48:58]);key=hd[:16].strip().decode();v=data[i+60:i+60+n]
        if key=='//':nms=v
        elif key.startswith('/')and key[1:].isdigit():
            j=int(key[1:]);key=nms[j:nms.index(b'/\n',j)].decode()
        else:key=key.removesuffix('/')
        result.append([key,n,H(v)]);i+=60+n+(n%2)
    assert i==len(data);return result
def source(rv):
    assert git('rev-parse','HEAD').decode().strip()==u['pin'] and sha(w/u['file'])==u['edited'if rv else'original']
    assert [os.fsdecode(x) for x in git('diff','--name-only','-z').split(b'\0') if x]==(u['files']if rv else[])
    assert all(sha(w/n)==z for n,z in u['frozen_inputs'].items())
def run(args,d,name,stdin=None):
    z=subprocess.run(list(map(str,args)),input=stdin,cwd=w,env=env,capture_output=True);(d/(name+'.stdout')).write_bytes(z.stdout);(d/(name+'.stderr')).write_bytes(z.stderr)
    return {'status':z.returncode,'args':list(map(str,args)),'stdout':H(z.stdout),'stderr':H(z.stderr)},z.stdout,z.stderr
def suite(tag,rev):
    source(rev);d=root/tag;d.mkdir();(d/'trace').mkdir();cmd=u['command']
    monitor(['strace','-ff','-q','-s','131072','-e','trace=execve','-e','signal=none','-o',d/'trace/run',*cmd],d/'cargo.stdout',d/'cargo.stderr')
    msg=[json.loads(y)for y in(d/'cargo.stdout').read_bytes().splitlines()];assert msg[-1]=={'reason':'build-finished','success':True}
    arts=[v for v in msg if v['reason']=='compiler-artifact'];assert len(arts)==373
    workspace=[v for v in arts if v['package_id'].startswith('path+file://'+str(w)+'/')]
    jobs=trace.jobs(d);counts=dict(collections.Counter(j['kind']for j in jobs));put(d/'jobs.json',jobs)
    if 'repeat'in tag:assert not jobs and all(a['fresh']for a in arts),(counts,len(arts))
    r0=[f for v in arts for f in(v['filenames']+([v['executable']]if v['executable']else[]))]
    prod={str(f):trace.dig(f)for f in sorted(set(r0))};assert all(prod.values());put(d/'all-products.json',prod)
    ws=[];scope={}
    for a in workspace:
        files=a['filenames']+([a['executable']]if a['executable']else[]);target=a['target']['name']
        ent={'package_id':a['package_id'],'name':target,'kind':a['target']['kind'],'fresh':a['fresh'],'files':{n:prod[n]for n in files}}
        outdirs={Path(f).parent for f in files}
        ent['saved_objects']={str(obj):trace.dig(obj)for dr in outdirs for objd in dr.glob('*.rlink-objects') for obj in objd.glob('*.o')}
        if target in ('unicode_names2','unicode_names2_generator') and a['target']['kind']==['lib']:
            lib,=[Path(n)for n in files if n.endswith('.rlib')];md,=[Path(n)for n in files if n.endswith('.rmeta')]
            rc,hdr,_=run(['rustc','+ohm','-Zls=root',md],d,'header-'+target);assert rc['status']==0
            m=re.search(rb'^private hash ([0-9a-f]{32}) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]{32})',hdr,re.M);assert m
            scope[target]={'rlib':keep(lib),'rmeta':keep(md),'members':ar(lib),'hash':[a.decode()for a in m.groups()],'lib_path':str(lib),'md_path':str(md)}
        ws.append(ent)
    put(d/'workspace-products.json',ws);put(d/'unicode-native.json',scope)
    sc,=[v for v in msg if v['reason']=='build-script-executed' and (v['package_id'].split('#')[0]).endswith('/ruff_unicode_names2')]
    g=Path(sc['out_dir']);gen={n:keep(g/n)for n in ['generated.rs','generated_alias.rs','generated_phf.rs']}
    logs={k:keep(g.parent/k) for k in ('output','stderr','root-output') if (g.parent/k).is_file()}
    put(d/'generated.json',{'typed':sc,'files':gen,'build_script_outputs':logs})
    path,=[v['executable']for v in arts if v['target']['name']=='ruff'and v['target']['kind']==['bin']]
    cli={}
    for key,src,status in [('good',b'x = "\\N{SNOWMAN}"\nprint(x)\n',0),('bad',b'x = "\\N{THIS IS NOT AN OFFICIAL UNICODE NAME}"\n',1)]:
        cfg=[path,'check','--isolated','--no-cache','--output-format','json','--stdin-filename','probe.py','-']
        o,so,se=run(cfg,d,'ruff-'+key,src);di=json.loads(so);assert o['status']==status and ((not di)if key=='good'else any(x['code']=='invalid-syntax'for x in di)),(o,di)
        cli[key]={'run':o,'source':src.decode(),'diagnostics':di}
    fresh1=None
    if 'repeat'not in tag:
        dirs=sorted({str(Path(f).parent)for f in r0});lib=scope['unicode_names2']['lib_path'];ex=out/'native-oracle'
        cmd=['rustc','+ohm','--edition=2024',q/'ops/unicode-reader.rs','--extern','unicode_names2='+lib,*[v for y in dirs for v in('-L','dependency='+y)],'-o',ex]
        c,_,se=run(cmd,d,'reader-build');assert c['status']==0,se[-600:]
        y,stdout,se=run([ex],d,'reader');assert y['status']==0 and b"'A' LATIN CAPITAL LETTER A" in stdout and b"LF alias and absent spelling checked" in stdout and not se
        cu=out/'unicode_caller.rs';cu.write_text('fn main() { let _name = unicode_names2::name(); }\n')
        bad=[*cmd[:3],'--error-format=json','--emit=metadata',str(cu),*cmd[4:-2],'-o',str(out/'bad.rmeta')]
        c2,_,se=run(bad,d,'reader-error');di=[json.loads(x)for x in se.splitlines()];assert c2['status']==1 and any((m.get('code')or{}).get('code')=='E0061'for m in di)
        fresh1={'compile':c,'native':y,'elf':sha(ex),'negative_args':c2}
    put(d/'controls.json',{'ordinary_caller':fresh1,'cli':cli})
    summary={'tag':tag,'rev':rev,'counts':counts,'units':len(arts),'fresh':sum(a['fresh']for a in arts),'source':sha(w/u['file']),'generator':scope['unicode_names2_generator']['hash'],'unicode':scope['unicode_names2']['hash'],'generated':gen,'procs':[[j['kind'],j['name']]for j in jobs],'cli_elf':sha(path),'space':guard()}
    put(d/'result.json',summary);print(tag,counts,summary['generator'],summary['unicode'],[(n,v['sha'][:12])for n,v in gen.items()],flush=True)
    trace.latest.update(prod)
    for j in jobs:
        if j['kind']in('full','partial'):trace.latest.update(j['products']);trace.latest.update({v['path']:v['after']for v in j['externs'].values()})
with(p/'native-measure.lock').open('rb')as lk:
    fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
    actual={k:sha(f)for k,f in {'cargo':sdk/'bin/cargo','rustc':sdk/'bin/rustc','driver':next((sdk/'lib').glob('librustc_driver-*.so')),'wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}.items()};assert actual==u['release']
    source(False);go(['git','apply','-R','--check',q/'ops/unicode.patch'])
    put(root/'bound.json',{'verified':actual,'package':'ruff','suite':u,'storage':guard()})
    for tag in u['order']:
        if tag=='edited':go(['git','apply','-R',q/'ops/unicode.patch'])
        if tag=='restored':go(['git','apply',q/'ops/unicode.patch'])
        suite(tag,tag.startswith('edited'))
    source(False);put(root/'complete.json',{'stages':u['order'],'pin':u['pin'],'status':0,'space':guard()})
