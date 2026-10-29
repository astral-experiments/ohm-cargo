"""Reopen original kernel records for the post-link wrapper and symlink boundaries."""
import argparse
import collections
import gzip
import hashlib
import json
import re
import tarfile
from pathlib import Path


def sha(b):return hashlib.sha256(b).hexdigest()
def read_tar(path):
    with tarfile.open(path) as t:
        return {p.name.removeprefix('reports/'):t.extractfile(p).read() for p in t if p.isfile()}


def supplement(root):
    arc=root/'supplement-v1/raw.tgz';assert sha(arc.read_bytes())=='47c2ea6c4242e410ab221341e1e3aa22b4de3798284df0386fa2a3446167ac07';records=read_tar(arc)
    term=json.loads(records['terminal.json']);assert len(term['cases'])==18
    expected={'default/cold':(0,17),'default/remove-executable':(101,17),'default/recover-executable':(0,29),'default/bitcode-cleanup':(0,31),'default/bad-bitcode':(101,31),'default/object-symlink':(101,31),'default/object-fifo':(101,31),'default/object-permission':(101,31),'default/recipe-symlink':(101,31),'default/recipe-fifo':(101,31),'default/recipe-missing':(101,31),'default/restore-supplied-manifest':(0,39),'default/zero-objects':(0,39),'default/recover-zero-objects':(0,41),'default/manifest-dir':(101,41),'explicit-no/cold':(0,17),'explicit-no/remove-executable':(0,17),'explicit-no/recover':(0,30)}
    assert expected.keys()==term['cases'].keys();stream_count=0
    for k,h in term['cases'].items():
        data=records[k+'/result.json'];assert sha(data)==h;j=json.loads(data);assert (j['cargo_exit'],j['old_public_value'])==expected[k]
        assert j['native_links']==1 and j['rustc_exit']==0 and j['inner_program']==j['compiler_requested_value']
        js=[json.loads(l) for l in records[k+'/stdout'].splitlines()];assert js[-1]['success']==(j['cargo_exit']==0)
        for n,field in [('stdout','stdout'),('stderr','stderr'),('wrapper.json','wrapper')]:assert sha(records[k+'/'+n])==j['raw'][field]
        parts=[]
        for f,digest in sorted(j['raw']['threads'].items()):
            b=gzip.decompress(records[k+'/'+f+'.gz']);assert sha(b)==digest;parts.append(b)
        stream_count+=len(parts);assert sha(b''.join(parts))==j['raw']['trace_sha256'];text=b''.join(parts).decode()
        assert any('execve(' in l and '/wild-ld/ld.bfd"' in l and l.rstrip().endswith('= 0') for l in text.splitlines())
        if k=='default/bad-bitcode':assert re.search(r'unlink\("[^"\n]*/inserted-probe\.bc"\)\s+= -1 EISDIR',text)
        if k=='default/bitcode-cleanup':assert re.search(r'unlink\("[^"\n]*/inserted-probe\.bc"\)\s+= 0',text) and j['post_bc']=='missing'
        if k.endswith(('object-symlink','recipe-symlink','object-permission')):
            err='EACCES' if k.endswith('permission') else 'ELOOP';assert any('openat(' in l and 'O_NOFOLLOW' in l and 'O_NONBLOCK' in l and '= -1 '+err in l for l in text.splitlines())
        if k.endswith(('object-fifo','recipe-fifo')):assert b'expected a regular file' in records[k+'/stderr']
        if k=='default/remove-executable':assert b'No such file or directory' in records[k+'/stderr'] and j['inner_program']==29
        if k=='default/zero-objects':assert j['post_manifest']=='missing' and j['inner_program']==40
        if k=='default/restore-supplied-manifest':assert j['post_manifest']=='regular' and j['manifest_proof']=='absent'
        if k=='default/manifest-dir':assert b'Is a directory' in records[k+'/stderr'] and j['post_manifest']=='directory'
    assert stream_count==620
    return {'commands':18,'kernel_streams':stream_count,'archive_sha256':sha(arc.read_bytes())}


def normalize_one(arm,label,d,records,protected):
    stem=arm+'/'+label+'/'
    for n in ('stdout','stderr'):assert sha(records[stem+n])==d['streams'][n]
    msgs=[json.loads(l) for l in records[stem+'stdout'].splitlines()];assert msgs[-1]=={'reason':'build-finished','success':True} and d['cargo_code']==0
    artifacts=[m for m in msgs if m['reason']=='compiler-artifact'];assert len(artifacts)==1 and not artifacts[0]['fresh']
    manifest=d['instance']['manifest'];sentinel=d['instance']['sentinel'];events=[];tools=collections.Counter();threadsha=[]
    for name,h in sorted(d['streams']['threads'].items()):
        lines=gzip.decompress(records[stem+name+'.gz']);assert sha(lines)==h;threadsha.append(h)
        for l in lines.decode().splitlines():
            timed,space,s=l.partition(' ');assert space
            if 'execve(' in s and s.rstrip().endswith('= 0'):
                tool=re.search(r'execve\("([^"]+)"',s)
                if tool:
                    base=Path(tool[1]).name
                    if '"--crate-name", "viewer"' in s and base in ('rustc','after-real-rustc'):tools[base]+=1
                    if base in ('ld','ld.bfd','ld.lld','rust-lld'):tools[base]+=1
            q=re.findall(r'"((?:[^"\\]|\\.)*)"',s);op=s.split('(',1)[0]
            if op in ('unlink','unlinkat') and q==[manifest] and s.rstrip().endswith('= 0'):action='unlink_manifest'
            elif op.startswith('readlink') and len(q)>=2 and q[0]==manifest and q[1]==sentinel and ' = -1' not in s:action='readlink_manifest_to_sentinel'
            elif op.startswith('symlink') and q==[sentinel,manifest] and s.rstrip().endswith('= 0'):action='install_link_to_sentinel'
            elif op.startswith('rename') and len(q)==2 and s.rstrip().endswith('= 0') and q[1] in (manifest,sentinel):
                assert q[0]!=q[1] and q[0].startswith(q[1]);action='replace_sentinel' if q[1]==sentinel else 'replace_manifest'
            else:continue
            events.append((timed,name,action,sha(l.encode()+b'\n')))
    events.sort();actions=[e[2]for e in events];subgroup=d['group'];intervention=d['intervention']
    assert tools['rustc']==1 and tools['after-real-rustc']==(subgroup!='ordinary')
    if subgroup=='defaults-off' and arm=='package19':assert tools['ld.lld']==tools['rust-lld']==1
    elif subgroup=='defaults-off':assert tools['ld']==1 and tools['ld.bfd']==0
    else:assert tools['ld.bfd']==1
    overwritten=not protected and intervention in ('watcher','wrapper') and subgroup in ('ordinary','post-rustc')
    assert d['sentinel_replaced']==overwritten and d['before']['uid']==d['after']['uid']==1000 and d['actual_program'] in (17,29,31)
    if overwritten:
        assert 'readlink_manifest_to_sentinel' in actions and actions[-1]=='replace_sentinel' and d['manifest_after']=='symlink'
        assert d['before']['ino']!=d['after']['ino'] and d['before']['sha256']!=d['after']['sha256']
        raw=records[stem+'sentinel-new.json'];assert sha(raw)==d['manifest_sha256']==d['after']['sha256'];meta=json.loads(raw);assert meta['objects'] and meta['rlink']['path'] and meta['executable']['path']
        assert [e[1] for e in events if e[2]=='readlink_manifest_to_sentinel'][-1]==events[-1][1]
    else:
        assert 'replace_sentinel' not in actions and 'readlink_manifest_to_sentinel' not in actions and d['before']==d['after']
        if subgroup in ('ordinary','post-rustc'):assert d['manifest_after']=='regular' and actions[-1]=='replace_manifest'
        else:assert d['manifest_after']=='symlink' and actions[-1]=='install_link_to_sentinel'
    if intervention=='watcher':
        assert d['observer']['event']=='IN_DELETE' and d['observer']['manifest_absent_before_install'] and d['observer']['euid']==1000 and actions[0]=='unlink_manifest' and not d['rustc_was_wrapped']
    if intervention=='preexisting':assert actions[0]=='unlink_manifest' and d['actual_program']==31
    if intervention=='wrapper':assert 'install_link_to_sentinel' in actions
    groupids={}
    event_summary=[]
    for _,tid,action,h in events:
        groupids.setdefault(tid,len(groupids));event_summary.append({'actor':groupids[tid],'action':action,'raw_line_sha256':h})
    return {'arm':arm,'group':subgroup,'phase':d['phase'],'intervention':intervention,'flags':d['flags'],'cargo_exit':d['cargo_code'],'program':d['actual_program'],'elf_sha256':d['program_elf'],'execs':dict(tools),'wrapped_rustc':d['rustc_was_wrapped'],'uid':d['before']['uid'],'sentinel_before_sha256':d['before']['sha256'],'sentinel_after_sha256':d['after']['sha256'],'sentinel_before_bytes':d['before']['bytes'],'sentinel_after_bytes':d['after']['bytes'],'inode_changed':d['before']['ino']!=d['after']['ino'],'sentinel_replaced':overwritten,'manifest_after':d['manifest_after'],'manifest_sha256':d['manifest_sha256'],'kernel':event_summary,'watcher_received_in_delete':intervention=='watcher','stdout':d['streams']['stdout'],'stderr':d['streams']['stderr'],'raw_record_sha256':sha(records[stem+'result.json']),'kernel_stream_sha256':threadsha}


def sentinel(root,green=None):
    refs={'sentinel-v2':'eeeb6fa4d71a3df3e3b00101badd059df289f92ad72fe1d87439f9e500f47a92','sentinel-v3':'4753f4fb6c8e730471ff236a010230cc1a1d7fdc5ddb8396b8c4c43141852ece'}
    if green is not None:refs['sentinel-green-v1']=green
    rows={};observed={};labels={'ordinary/cold','ordinary/observer-after-delete','ordinary/preexisting-before','post-rustc/cold','post-rustc/after','explicit-no/cold-after','defaults-off/cold-after'}
    for name,h in refs.items():
        arc=root/name/'raw.tgz';assert sha(arc.read_bytes())==h;rec=read_tar(arc);protected=name.startswith('sentinel-green')
        if 'terminal.json' in rec:
            t=json.loads(rec['terminal.json']);assert all(sha(rec[l+'/result.json'])==v for l,v in t['cases'].items());observed[name]=t['subjects']
        else:assert name=='sentinel-v2' and 'AssertionError:' in (root/name/'acquisition.stderr').read_text()
        cases=[n for n in rec if n.endswith('/result.json')]
        if name=='sentinel-v2':assert len(cases)==13
        if name=='sentinel-v3':assert cases==['candidate282/defaults-off/cold-after/result.json']
        if protected:assert len(cases)==7 and (root/name/'acquisition.exit').read_bytes()==b'0\n'
        for path in sorted(cases):
            prefix=path.removesuffix('/result.json');arm,case=prefix.split('/',1);d=json.loads(rec[path]);r=normalize_one(arm,case,d,rec,protected)
            index=('fixed/'+case if protected else prefix);assert index not in rows;r['arm']='fixed' if protected else arm;rows[index]=r
    for a in ('package19','candidate282')+(('fixed',)if green else ()):
        assert {k.split('/',1)[1]for k in rows if k.startswith(a+'/')}==labels
    assert sum(r['sentinel_replaced'] for r in rows.values())==4
    subjects={'package19':{'source':'235f9228651b74c591e6f62cae4c9b761448dd2d','archive':'ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812','cargo':'789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1','rustc':'5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511','driver':'f772b49abec18759edbd9cb7f9f2930097d6ba64d9a2b82837edf4451acc3014','wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'},'candidate282':dict(observed['sentinel-v3']['candidate282'],source='34f497bc7a9beb1b91990e737d86a2c520664d39',binary_version_stamp='34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31')}
    if green is not None:
        subjects['fixed']=dict(observed['sentinel-green-v1']['candidate282'],source='5394ce8817e224971230b80a9066cc28d504ff94',source_tree='3157f963855bcd1cdc9c5512611aaf81bdf8b984',build_receipt='cfcce32f9ca4e446249eb22d0bcf5ab3d1af2b3b189c894a854a1b23ed5087a3')
        assert subjects['fixed']['cargo']=='5cc0517d944c86d10dd8595ee8941f33ad5b15183fd56493cb799e3222b44021' and all(subjects['fixed'][k]==subjects['candidate282'][k] for k in ('rustc','driver','wild'))
        for case in labels:assert rows['candidate282/'+case]['elf_sha256']==rows['fixed/'+case]['elf_sha256']
    standalone={}
    if green is not None:
        for n,original in [('portable19',True),('portable-fixed',False)]:
            where=root/'sentinel-green-v1';output=(where/(n+'.stdout')).read_bytes();assert (where/(n+'.exit')).read_bytes()==b'0\n' and not (where/(n+'.stderr')).read_bytes()
            sub=json.loads(output);assert [(r['phase'],r['program']) for r in sub]==[('cold',17),('during',29),('before',31)]
            for r in sub:assert r['sentinel_replaced']==(r['phase']=='during' and original) and r['manifest_is_symlink']==r['sentinel_replaced'] and (r['sentinel_sha256_before']!=r['sentinel_sha256_after'])==r['sentinel_replaced']
            standalone[n]={'stdout_sha256':sha(output),'exit':0,'stderr_sha256':sha(b''),'rows':sub}
    return {'archives':refs,'diagnostic_first_archive':'a4823a96e5af8ac2ce6749748db3853786098f4a0c0b5c458c42f0c836554bf3','subjects':subjects,'rows':rows,'standalone_no_wrapper':standalone}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--green-raw-sha');p.add_argument('--export',type=Path);p.add_argument('--only-sentinel',action='store_true');args=p.parse_args()
    primary=None if args.only_sentinel else supplement(args.root);sol=sentinel(args.root,args.green_raw_sha)
    if args.export:args.export.write_bytes(gzip.compress(json.dumps(sol,sort_keys=True,separators=(',',':')).encode()+b'\n',mtime=0))
    print(json.dumps({'wrapper':primary,'symlink_cases':len(sol['rows']),'sentinels_replaced':sum(v['sentinel_replaced']for v in sol['rows'].values()),'green':args.green_raw_sha},sort_keys=True))
