"""Assemble public-safe filesystem, native, compiler and diagnostic receipts from the unscored H5 trial."""
from pathlib import Path
import collections,gzip,hashlib,json,os,re,runpy,sys,tarfile
HERE=Path(__file__).resolve().parent;g=runpy.run_path(HERE/'runner.py');join=runpy.run_path(HERE/'joins2.py')['join'];D,O,W,H,h,save=[g[a] for a in ['D','O','W','H','h','save']]
def read(f):return json.loads(f.read_text())
class Clean:
    def __call__(self,v):
        if isinstance(v,dict):return {self(k):self(x) for k,x in v.items()}
        if isinstance(v,list):return [self(t)for t in v]
        if not isinstance(v,str):return v
        v=v.replace(str(D),'@cache').replace(str(W),'@ruff').replace(str(H),'@home')
        v=re.sub(r'((?:^|/)registry/(?:src|cache|index)/)[^/ :\n]+(?=/|$)', r'\1@registry',v)
        for host in filter(None,os.environ.get('OHM_EXPORT_REGISTRY_ALIASES','').split(',')):
            v=v.replace(host,'@registry')
        return v
clean=Clean()
def rows_for(mode,st,tag):
    b=O/mode/st/tag;hist=read(b/'receipt.json');files=read(b/'files.json');arts=read(b/'artifacts.json');procs=read(b/'calls.json');diag=read(b/'diagnostics.json');census=read(b/'census.json') if (b/'census.json').is_file() else (read(O/mode/'seed-census.json') if st=='seed' and tag==read(O/mode/'seed-complete.json')['final'] else None);cmdc=collections.Counter(v['role'] for v in procs)
    assert hist['physical']==dict(cmdc)
    cards=collections.Counter();_h=collections.Counter()
    for v in arts:
        if v['exe']:
            cards['all-executable-records']+=1;cards['test-profile-executable' if v['profile'].get('test')else 'other-executable']+=1
        _h[(v['name'],tuple(v['kind']),bool(v['profile'].get('test')))] += 1
    pr={'receipt':hist,'protocol-original-shas':{f.name:h(f)for f in b.iterdir()if f.name in ['receipt.json','artifacts.json','files.json','census.json','diagnostics.json','scripts.json','calls.json','exec-ledger.json','other-execs.json','cargo.stderr','cargo.stdout.ndjson']},'products':files,'diagnostics':diag,'executable-artifact-profiles':dict(cards),'unit-roster':[{'name':a['name'],'pkg':(a['pkg'].split('#',1)[-1] if not a['pkg'].startswith('path+')else 'workspace/'+a['source'].removeprefix(str(W)+'/').split('/')[1]),'kind':a['kind'],'test_profile':bool(a['profile'].get('test')),'fresh':a['fresh'],'files':a['files'],'exe':a['exe']}for a in arts],'all-physical-typed-processes':procs}
    # Only bytes, category and hash are retained for encoded records. No raw source paths or environment values.
    pr['wire-records']=census
    if st!='seed':
        ed=O/mode/st/(tag+'-readers')/'result.json';pr['ordinary-readers']=read(ed);pr['ordinary-reader-raw-result-sha']=h(ed)
        ch=b/'products-changed-vs-seed.json';pr['changed-products']=read(ch)
    if tag!='cold' and census is not None:pr['compiler-record-joins']=join(mode,st,tag)
    return clean(pr)
def summarize(r):
    h=r['receipt'];cards=r['executable-artifact-profiles'];c=(r['wire-records']['counts'] if r['wire-records'] is not None else None);meta={'units':h['units'],'fresh':h['fresh'],'status':h['exit'],'processes':h['physical'],'diagnostics':h['diag'],'file_count':h['native_hash_rows'],'all_ELF_files':h['elf'],'artifact_profile_counts':cards,'encoded_classes':c}
    if j:=r.get('compiler-record-joins'):
        meta.update({'actual-jobs-by-old-class':j['jobs_by_old_class'],'record-transitions':j['mutated_records_by_before_after_class'],'new-record-ids':len(j['new_record_ids']),'initial_inventory_by_source':j['seed_capabilities_by_compiler_source']})
    if 'changed-products' in r:
        n=r['changed-products'];meta['changed-output-paths']=len(n);meta['changed-ELF']=sorted(k for k,v in n.items() if (v.get('before')or{}).get('elf')or(v.get('after')or{}).get('elf'));meta['ordinary-readers']={k:{n:v[n]for n in ('exit','stdout_sha','stderr_sha','output_hash','names','error_message')if n in v}for k,v in r['ordinary-readers'].items()}
    return meta
def main():
    version=sys.argv[1];assert re.fullmatch(r'control-v\d+|complete-v\d+',version);out=D/'exports'/version;out.mkdir(parents=True)
    allout={};orig={}
    for mode in ('check','build','test'):
        cells=list(sorted((O/mode/'seed').glob('noop-*')))
        if not cells:raise AssertionError(mode)
        paths=[('seed','cold')]+[('seed',z.name)for z in cells]
        for st in ('stock-repeat','upgraded')if version.startswith('complete')else ('stock-repeat',):
            for t in ('first','second','third-if-displaced'):
                if t!='third-if-displaced' or (O/mode/st/t/'receipt.json').is_file():paths.append((st,t))
        summaries={}
        for st,t in paths:
            q=rows_for(mode,st,t);summaries[st+'/'+t]=summarize(q)
            name=mode+'-'+st+'-'+t+'.json.gz';data=(json.dumps(q,sort_keys=True,indent=2)+'\n').encode()
            assert b'credentials.toml' not in data.lower() and not re.search(
                rb'bearer\s+\S+|gh[pousr]_[a-z0-9]{16,}|://[^/ :\s]+:[^/ @\s]+@',data,re.I)
            (out/name).write_bytes(gzip.compress(data,compresslevel=6,mtime=0))
            assert (out/name).stat().st_size<7*2**20
        allout[mode]=summaries
        orig[mode]={v:read(O/mode/(v+'.json'))for v in ('seed-tree','stock-repeat-input-tree','upgraded-input-tree')}
    save(out/'results.json',allout);save(out/'clone-bindings.json',orig);save(out/'official16.json',read(D/'release.json'))
    for p in out.iterdir():assert p.stat().st_size<8*2**20
    print(json.dumps({m:{k:[v['fresh'],v['processes']]for k,v in r.items()}for m,r in allout.items()},sort_keys=True))
if __name__=='__main__':main()
