"""Check the measured state/proc/ELF contract and recompute the complete fixed 16-pair study."""
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import argparse,csv,hashlib,itertools,json,math,statistics
from common import load,dump,sha,need,trace
from witness import as_digest

H=Path(__file__).resolve().parent; reg='9b0e4509b59703a7d6d3f517990067dd0d3b980ed7d97ba98253927099401eae'

def numbers(rows):
    stats={}
    for mode in ['test','build']:
        series=[r for r in rows if r['mode']==mode];need(len(series)==32,'complete paired data')
        med={a:statistics.median(r['elapsed_ns'] for r in series if r['arm']==a)/1e6 for a in 'VC'};ratios=[];orders=[]
        for i in range(1,17):
            q=[r for r in series if r['block']==i];need(len(q)==2 and q[0]['order']==q[1]['order'],'pair');order=q[0]['order']; vals={r['arm']:r['elapsed_ns'] for r in q};ratio=math.log(vals['V']/vals['C']);ratios.append(ratio);orders.append(order)
        need(orders.count('VC')==orders.count('CV')==8,'balanced order')
        pct=sorted(-100*math.expm1(-r) for r in ratios);item={'n':16,'v3_median_ms':med['V'],'stack_median_ms':med['C'],'paired_median_reduction_pct':statistics.median(pct),'paired_median_interval_pct':[pct[3],pct[12]],'favorable_pairs':sum(v>0 for v in pct),'min_pct':pct[0],'max_pct':pct[-1]}
        if mode=='test':
            chron=[r if o=='VC' else -r for r,o in zip(ratios,orders)];total=hits=0;target=sum(ratios)
            for perm in itertools.combinations(range(16),8):
                keep=set(perm);hits+=sum(x if i in keep else -x for i,x in enumerate(chron))>=target-1e-12;total+=1
            p=hits/total;item.update(one_sided_exact_randomization_p=p,enumerated=total,upper_tail=hits,qualified=bool(p<.05 and pct[3]>0 and item['favorable_pairs']>=13))
        else:item['noninferior_at_five_percent']=bool(pct[3]>-5)
        stats[mode]=item
    return stats

def normalize_exec(p):
    if p.endswith('/bin/cargo'):return 'cargo-proxy-or-installed'
    if p.endswith('/bin/rustc'):return 'rustc'
    return Path(p).name

def extract(base):
    plan=load(H/'ruff-prefetch-registration.json');need(sha(H/'ruff-prefetch-registration.json')==reg,'plan');run=load(base/'complete.json');need(run['timed']==run['audited']==64 and run['source_clean'],'run');rows=[];audit=[];anchors={};training={};controls={}
    for mode in ['test','build']:
        a=load(base/('anchor-'+mode+'-V')/'anchor.json');anchors[mode]=a
        for arm in 'VC':
            for phase in ['anchor','final']:
                b=load(base/(phase+'-'+mode+'-'+arm)/'anchor.json');need(all(a[k]==b[k] for k in ('stamps','proofs','raw_sha256','roster_sha256','message_sha256','cache_inventory','diagnostics')),'anchor drift');need(all(n['trusted'] for n in b['cargo_home_ancestors']),'manifest cache ownership')
            controls[mode+'-'+arm]=load(base/('prepare-'+mode+'-'+arm)/'receipt.json')['dirty']
        training[mode+'-prior']=load(base/('prior-unscored-'+mode+'.json'))
    for block in plan['orders']:
        for mode in block['endpoint_order'].split(','):
            a=anchors[mode]
            for arm in block[mode]:
                id=f"{block['block']:02d}-{mode}-{arm}";native=load(base/('timed-'+id)/'receipt.json');d=base/('audit-'+id);aud=load(d/'receipt.json');need(native['normal_terminal'] and not native['executable_open_events'] and not aud['normal_terminal'],'ordinary gate');need(native['cargo_sha256']==aud['cargo_sha256']==plan['subjects']['cargo_'+('control' if arm=='V' else 'candidate')]['sha256'],'cargo image')
                for rr in [native,aud]:
                    need(rr['status']==0 and rr['pre_proof_sha256']==rr['post_proof_sha256']==as_digest(a['proofs']) and rr['pre_stamp_sha256']==rr['post_stamp_sha256']==as_digest(a['stamps']),'ELF/OBS1 gate')
                physical=trace(d);need(physical==aud['processes'],'raw exec audit');need(aud['units']==(619 if mode=='test' else 501) and aud['roster_sha256']==a['roster_sha256'] and not(aud['dirty'] or physical['rustc'] or physical['rustc_queries'] or physical['linkers'] or physical['target_execs']),'audit did work')
                rows.append({'block':block['block'],'mode':mode,'order':block[mode],'arm':arm,'elapsed_ns':native['ns'],'status':native['status'],'obs_prepost':native['pre_proof_sha256'],'elf_prepost':native['pre_stamp_sha256'],'native_image_opens':len(native['executable_open_events']),'verified_fresh_units':aud['units'],'audited_roster':aud['roster_sha256'],'audited_jobs':len(physical['rustc']),'audited_queries':len(physical['rustc_queries']),'audited_links':len(physical['linkers']),'checksum_workers':len(aud['checksum_worker_starts'])})
                audit.append({'block':block['block'],'mode':mode,'arm':arm,'images':[normalize_exec(n) for _,n in physical['executions']],'worker_starts':len(aud['checksum_worker_starts']),'raw_exec_rows':len(physical['executions'])})
    for arm in 'VC':
        p=base/('training-'+arm+'.json');
        if p.exists():training[arm]=load(p)
    summary={m:{'roster':a['roster_sha256'],'messages':a['message_sha256'],'units':a['units'],'workspace_elfs':{Path(p).name:sha for p,sha in a['raw_sha256'].items()},'elf_count':len(a['elf']),'executable_count':len(a['executables']),'identity_sha256':as_digest(a['stamps']),'observer_sha256':as_digest(a['proofs']),'reader_files':[{'name':r['name'],'encoded':r['sha256'],'raw':r['raw_sha256'],'complete':r['complete']} for r in a['proofs']],'cache':a['cache_inventory'],'prelaunch':{k:v for k,v in controls.items() if k.startswith(m)},'full_dep_files_scanned':a['scanned_compiler_dep_info']} for m,a in anchors.items()}
    # Preserve relative path when different binaries carry the same basename.
    for m,a in anchors.items():
        make_relative=lambda p:p.split('/native-target/',1)[1] if '/native-target/' in p else p.split('/shared/',1)[-1]
        summary[m]['workspace_elfs']={make_relative(p):v for p,v in a['raw_sha256'].items()};need(len(summary[m]['workspace_elfs'])==summary[m]['elf_count'],'ELF relative path collision')
    return rows,audit,summary,training

def verify_saved(dest):
    plan=load(dest/'ruff-prefetch-registration.json');need(sha(dest/'ruff-prefetch-registration.json')==reg,'published plan');
    with (dest/'wall.csv').open() as f:
        rr=list(csv.DictReader(f))
    for p in rr:
        for k in ('block','elapsed_ns','status','native_image_opens','verified_fresh_units','audited_jobs','audited_queries','audited_links','checksum_workers'):p[k]=int(p[k])
    need(len(rr)==64,'rows');a=load(dest/'anchors.json');execs=load(dest/'execs.json');need(len(execs)==64,'exec count')
    for row in rr:
        mode=row['mode'];n=row['block'];ar=row['arm'];ref=a[mode];need(row['order']==plan['orders'][n-1][mode] and row['status']==row['native_image_opens']==row['audited_jobs']==row['audited_queries']==row['audited_links']==0,'native/trace');need(row['obs_prepost']==ref['observer_sha256'] and row['elf_prepost']==ref['identity_sha256'] and row['audited_roster']==ref['roster'],'anchor');need(row['verified_fresh_units']==ref['units']==(619 if mode=='test' else 501),'full roster');need(ref['elf_count']==len(ref['workspace_elfs'])==(110 if mode=='test' else 15),'full ELF');need(ref['executable_count']==(102 if mode=='test' else 6),'full executable');ext=[e for e in execs if e['mode']==mode and e['arm']==ar and e['block']==n];need(len(ext)==1 and ext[0]['worker_starts']==row['checksum_workers'] and ext[0]['raw_exec_rows']==len(ext[0]['images']) and 'rustc' not in ext[0]['images'],'no native rustc');
    need(len(a['test']['reader_files'])==1 and a['test']['reader_files'][0]['complete'],'Ron proof');scores=numbers(rr);need(scores==load(dest/'statistics.json'),'recomputed scores');return scores

if __name__=='__main__':
    c=argparse.ArgumentParser();c.add_argument('--raw',type=Path);c.add_argument('--public',type=Path,required=True);args=c.parse_args();d=args.public
    if args.raw:
        d.mkdir();rows,execs,anc,training=extract(args.raw);import shutil;shutil.copyfile(H/'ruff-prefetch-registration.json',d/'ruff-prefetch-registration.json');dump(d/'execs.json',execs);dump(d/'anchors.json',anc);dump(d/'training.json',training);dump(d/'statistics.json',numbers(rows));
        with (d/'wall.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(verify_saved(d),indent=2))
