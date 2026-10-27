"""Match actual full or link-only rustc execs to original dep-info records via real -Cextra-filename."""
import ast,collections,hashlib,json,os,re,sys
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/cargo-checksum-migration-20261027-v1');E=P/'evidence'
def H(b):return hashlib.sha256(b).hexdigest()
def read(f):return json.loads(f.read_text())
def id_of(k):
    pts=Path(k).parts
    if pts[-2]=='fingerprint' and re.fullmatch('[0-9a-f]{16}',pts[-3]):return pts[-3]
    old=re.search(r'-([0-9a-f]{16})$',pts[-2]);return old[1] if old else None
def parse_rec(q):
    rows=[]
    for c in read(q/'calls.json'):
        if c['role'] not in ('rustc-full','rustc-link-only'):continue
        p=q/('exec.'+str(c['pid']));assert H(p.read_bytes())==c['raw_file_sha256']
        a=None
        for line in p.read_text(errors='replace').splitlines():
            m=re.match(r'^execve\("([^"]+)", (\[.*\]), .+ = 0$',line)
            if m and H(m[2].encode())==c['arg_sha256']:a=ast.literal_eval(m[2]);break
        assert a is not None
        ids=[v.split('=-',1)[1] for v in a if v.startswith('extra-filename=-') and re.fullmatch('extra-filename=-[0-9a-f]{16}',v)]
        if not ids:
            ids=list({m[1]for v in a if (m:=re.search(r'-([0-9a-f]{16})\.rlink$',v))})
        assert len(ids)<=1,ids
        derived_from='extra-filename-or-rlink'
        if '--out-dir'in a:
            od=Path(a[a.index('--out-dir')+1])
            if od.name=='out' and re.fullmatch('[0-9a-f]{16}',od.parent.name):
                if ids and ids[0]!=od.parent.name:derived_from='actual-out-dir-overrides-file-suffix'
                else:derived_from='actual-out-dir'
                ids=[od.parent.name]
        if not ids:
            refs=[Path(v)for v in a if v.endswith('.rlink')]
            ds={rr.parent.parent.name for rr in refs if rr.parent.name=='out' and re.fullmatch('[0-9a-f]{16}',rr.parent.parent.name)}
            if len(ds)==1:ids=list(ds);derived_from='actual-rlink-directory'
        src=c.get('source')or''
        rows.append({'pid':c['pid'],'role':c['role'],'crate':c['crate'],'exit':c['exit'],'id':ids[0]if ids else None,'workspace_source':src.startswith('crates/') or '/ruff-ohm-whole-native-20261027/crates/'in src,'argc':len(a),'argv_sha256':c['arg_sha256'],'id_basis':derived_from,'test':'--test'in a})
    return rows
def join(mode,st,tag):
    base=E/mode;src=read(base/'seed-census.json')['rows'];lookup={id_of(k):(k,v) for k,v in src.items()if id_of(k)}
    assert len(lookup)==len(src),(mode,'ambiguous fingerprint keys',len(lookup),len(src))
    pure=parse_rec(base/'seed/cold');real=collections.defaultdict(list)
    for c in pure:
        if c['id']:real[c['id']].append(c)
    classes=collections.Counter((rr['class'], 'workspace' if any(u['workspace_source']for u in real.get(k,[]))else ('external' if k in real else 'unmapped'))for k,(_,rr)in lookup.items())
    q=base/st/tag
    current=read(q/'census.json')['rows']if(q/'census.json').is_file()else src
    counts=collections.Counter();record_delta=collections.Counter();ids_changed=[]
    for k,old in src.items():
        new=current.get(k);newcl=new['class']if new else 'absent'
        if not new or new['sha256']!=old['sha256']:record_delta[(old['class'],newcl)]+=1;ids_changed.append(id_of(k))
    extra=[id_of(k)for k in current.keys()-src.keys()]
    tab={}
    for k,(x,rr)in lookup.items():
        p=Path(x);tab[k]={'unit':p.name,'package':p.parts[-4]if p.parts[-2]=='fingerprint' else p.parts[-2].rsplit('-',1)[0],'class':rr['class'],'old_sha256':rr['sha256'],'new_sha256':current[x]['sha256']if x in current else None,'workspace':any(z['workspace_source']for z in real.get(k,[])),'old_count_seen':len(real.get(k,[])),'current_class':current[x]['class']if x in current else 'absent'}
    physical=[]
    for c in parse_rec(q):
        info=tab.get(c['id'],{});c.update({'before_class':info.get('class','unmapped'),'after_class':info.get('current_class','unmapped'),'producer_pkg':info.get('package')});physical.append(c);counts[(c['role'],c['before_class'])]+=1
    def flatten(c):return {':'.join(k):v for k,v in sorted(c.items())}
    return {'entry_count':len(tab),'seed_capabilities_by_compiler_source':flatten(classes),'seed_unique_full_rustcs':len(real),'jobs_by_old_class':flatten(counts),'mutated_records_by_before_after_class':flatten(record_delta),'disappeared_or_changed_ids':sorted(z for z in ids_changed if z),'new_record_ids':sorted(z for z in extra if z),'physical':physical,'units':tab}
if __name__=='__main__':
    mode,st,t=sys.argv[1:];a=join(mode,st,t);print(json.dumps(a['seed_capabilities_by_compiler_source'],sort_keys=True));print(json.dumps(a['jobs_by_old_class'],sort_keys=True));d=E/mode/st/t/'joins-v2.json';d.write_text(json.dumps(a,sort_keys=True,indent=2)+'\n')
