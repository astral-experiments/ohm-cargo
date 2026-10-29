"""Offline semantic verifier and negative self-tests for the failed-producer recovery report."""
import argparse, copy, hashlib, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/name).read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(v, reason):
    if not v:raise ValueError(reason)
def check(m, c, cost, fifo, src):
    stock=src['compiler']['cargo'];fixed=src['final']['cargo']
    require(stock=='02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573','official compiler driver')
    require(src['final']['source']=='34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31' and src['final']['tree']=='bda3469e08fbde973f4d4df6ac6b6d29851ef82b' and src['final']['parent']==src['speculative_blocking_head'],'Git ancestry')
    require(src['final']['source'] in src['final']['version'][2] and sha(ROOT/'product.patch')==src['final']['source_patch'],'source artifact')
    require(src['older_correct']['head']['original_fixture_exit']==0 and src['older_correct']['seedparent']['original_fixture_exit']==0 and src['older_correct']['seeddefault']['errors']==['E0460'],'historical gate')
    units=[['dep','lib'],['app','lib'],['app','bin']]
    for arm in ['old-only','final-e']:
        for mode in ['default','mtime','checksums']:
            r=m[arm+'/'+mode];base=r['prime'];failed=r['forced-failure'];rev=r['reverted'];settled=r['settled']
            require(base['rustc']==units and base['rc']==0 and base['cargo']==stock,'real prime')
            require(failed['rustc']==units[:2] and failed['rc']==101 and failed['cargo']==stock,'real early dependent commit')
            a=base['producer'];b=failed['producer'];z=rev['producer']
            require((a['source'],b['source'],z['source'])==('pub const VALUE: i32 = 1;','pub const VALUE: i32 = 2;','pub const VALUE: i32 = 1;'),'real change and revert')
            for x in (a,b,z):require(hashlib.sha256(x['source'].encode()).hexdigest()==x['source_sha256'],'physical source')
            require(a['source_blake3']==z['source_blake3'] and a['source_blake3']!=b['source_blake3'],'independent source checksum')
            require(len(bytes.fromhex(a['short_hex']))==16 and b['short_hex']=='' and a['public_hex'] and b['public_hex'] is None,'absent committed producer identity')
            if mode!='mtime':
                for x in (a,b,z):
                    markers=re.findall(rb'blake3=([a-f0-9]{64})',bytes.fromhex(x['translated_hex']))
                    require(markers==[a['source_blake3'].encode()],'prior dep-info authenticates original bytes')
            else:require(b'blake3=' not in bytes.fromhex(a['translated_hex']),'ordinary mtime control')
            for k in ('app_rmeta','app_rlib','dep_rmeta','dep_rlib'):
                require(base['artifacts'][k]['sha256']!=failed['artifacts'][k]['sha256'],'real incompatible artifacts '+k)
            require(failed['artifacts']['app_marker']['size']==16 and failed['artifacts']['dep_marker']['size']==0 and failed['artifacts']['dep_rmeta']['mtime_ns']<=failed['artifacts']['app_rmeta']['mtime_ns'],'real committed middle')
            should_fail=arm=='old-only' and mode!='mtime'
            require(rev['cargo']==(stock if arm=='old-only' else fixed) and rev['rc']==(101 if should_fail else 0),'first-revert verdict')
            require(rev['rustc']==([units[0],units[2]] if should_fail else units) and rev['diagnostics']==(['E0460'] if should_fail else []),'first-revert jobs/diagnostic')
            if should_fail:
                require(rev['artifacts']['app_rmeta']==failed['artifacts']['app_rmeta'] and r['untouched-1']['rc']==0,'old middle physically retained')
            else:
                require(rev['artifacts']['app_rmeta']['sha256']==base['artifacts']['app_rmeta']['sha256'],'middle regenerated against correct producer')
            program=r['untouched-1-program'] if should_fail else r['reverted-program']
            require(program['output_hex']=='310a' and program['rc']==0 and r['settled-program']['output_hex']=='310a','real program output')
            require(settled['rustc']==[] and settled['rc']==0,'unchanged settling')
    for key,n in [('conditional-final-e',7),('headstart-final-e',2)]:
        require(c[key]['status']==0 and len(c[key]['cases'])==n and c[key]['cargo']==fixed,'unaltered integration suite')
    require(any('rebuilds_committed_dependent_after_failed_producer_is_reverted' in s for s in c['conditional-final-e']['cases']),'original regression test')
    require(c['whole-lib-tests']['passed']==407 and c['fingerprint-unit-tests']['passed']==84 and any('committed_short_hash_only_validates_one_current_comparison' in s for s in c['fingerprint-unit-tests']['cases']),'Cargo library suites')
    for order in ['first','late']:
        rows=c['trait-'+order]['rows']
        for n in ['edited','edited-repeat','edited-clean']:
            require(not rows[n]['success'] and rows[n]['errors']==[['client','E0034']],'actual leaf diagnostic')
        for n in ['original','original-repeat','restore','restore-repeat']:
            require(rows[n]['success'] and not rows[n]['errors'],'opposite source or restoration')
        for n in ['original-repeat','restore-repeat']:
            require(rows[n]['fresh']==['api','client','provider','reader'],'trait settles')
    for arm,numbers in [('B',[2,1,1]),('V1',[3,2,2]),('V2',[2,2,1]),('V3',[2,2,1]),('E',[2,2,1])]:
        for mode,n in zip(['default','nonexclusive','mtime'],numbers):
            d=cost['open-audit-v4/'+arm+'/'+mode];require(len(d['physical'])==4 and sorted(d['physical'].values())==[n]*4,'actual private opens')
            require(all(f for _,f in d['runs'][1]['units']),'all private artifacts fresh')
    for arm in ['B','Bdev','V2','V3','E']:
        for mode in ['shared-fine','non-ohm']:
            d=cost['registry-opens-v1/'+arm+'/'+mode];local=d['physical']['lib-workspace_local'];reg=d['physical']['lib-itoa']
            require(reg['reads']==(1 if mode=='non-ohm' else 2 if arm in ('B','Bdev') else 3),'genuine shared-registry opens')
            require(local['reads']==(1 if mode=='non-ohm' else 2),'genuine locked local opens')
            require(all(a[1] for a in d['runs'][1]['artifacts']) and any(a[0]=='itoa' and a[2] for a in d['runs'][1]['artifacts']),'actual registry package, all fresh')
            if mode=='shared-fine':require('/registries/' in reg['short_file'] and '/workspaces/' in local['short_file'],'actual workspace vs shared cache')
    require(cost['memo_layout']=={'value_bytes':16,'memo_value_bytes':16,'mutex_bytes':24,'memo_mutex_bytes':24,'align':8,'memo_align':8},'actual released Linux Rust layout')
    for arm in ('B','D','Efinal'):
        for mode in ('default','no-ohm'):
            def f(v):return fifo[arm+'/'+mode+'/'+v]
            a=f('alone');e=f('parent-error');l=f('long-parent-error');s=f('regular-symlink')
            require(a['deadline'] and a['writer_processes']==0 and a['fifo_open_calls']>0,'lone original owner FIFO')
            require((e['deadline'],e['parent_eisdir'])==((True,False) if arm=='D' else (False,True)),'original two-path failure')
            if arm=='B':require(e['fifo_open_calls']==0,'old skips FIFO entirely')
            if arm=='Efinal':require(e['rc']==101 and e['cargo']==fixed,'bounded refusal on exact candidate')
            require(l['rc']==101 and l['parent_eisdir'] and l['physical_short_size']==1048576 and l['read_bytes']==(1048576 if arm=='D' else 0),'bounded malformed input')
            require(s['rc']==0 and s['eligible_unit_fresh']==['api','client','provider','reader'],'valid symlink eligibility')
    return True
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--selftest',action='store_true');args=parser.parse_args()
    paths={}
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1)
        require(name not in paths and '/' not in name and name not in {'.','..'},'manifest path')
        paths[name]=digest
    require(set(paths)=={f.name for f in ROOT.iterdir() if f.is_file() and f.name!='SHA256SUMS'},'manifest inventory')
    for name,digest in paths.items():require(sha(ROOT/name)==digest,'checksum '+name)
    d=[read(n) for n in ['first-revert.json','controls.json','fresh-reads.json','special-files.json','source.json']];check(*d)
    if args.selftest:
        def mutate(*parts):
            z=copy.deepcopy(d);p=z
            for x in parts[:-2]:p=p[x]
            p[parts[-2]]=parts[-1]
            try:check(*z)
            except ValueError:return
            raise RuntimeError('invalid evidence accepted '+str(parts))
        mutate(0,'final-e/default','reverted','rc',101)
        mutate(0,'final-e/checksums','forced-failure','producer','short_hex','00'*16)
        mutate(0,'old-only/checksums','reverted','diagnostics',[])
        mutate(1,'trait-late','rows','edited','success',True)
        mutate(2,'registry-opens-v1/E/shared-fine','physical','lib-itoa','reads',2)
        mutate(3,'Efinal/default/parent-error','deadline',True)
        mutate(3,'Efinal/no-ohm/long-parent-error','read_bytes',1048576)
    print('Verified six first-revert histories, 14 E0034 checks, approved and rejected FIFO behavior, Cargo suites and physical read counts.')
if __name__=='__main__':main()
