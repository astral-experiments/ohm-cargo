"""Inspect every differing final ELF and run the same individually selected native test case on each image."""
from pathlib import Path
import collections,hashlib,json,mmap,os,re,runpy,subprocess,sys
p=Path(__file__).resolve().parent;g=runpy.run_path(p/'runner.py');elf=runpy.run_path(p/'elf-fields.py')['elf'];D,O,W,SDK,h,save,env,ns,tr=[g[k]for k in ['D','O','W','SDK','h','save','environment','ns','translate']]
load=lambda p:json.loads(p.read_text())
def raw_ranges(left,right):
    if left.stat().st_size!=right.stat().st_size:return {'equal_length':False}
    out=[];count=0;length=left.stat().st_size
    with left.open('rb')as a,right.open('rb')as b,mmap.mmap(a.fileno(),0,access=mmap.ACCESS_READ)as x,mmap.mmap(b.fileno(),0,access=mmap.ACCESS_READ)as y:
        for pos in range(0,length,64*1024):
            xx=x[pos:pos+65536];yy=y[pos:pos+65536]
            if xx==yy:continue
            for i,(l,r)in enumerate(zip(xx,yy),start=pos):
                if l==r:continue
                count+=1
                if len(out)>=4096:continue
                if out and out[-1][1]==i:out[-1][1]+=1
                else:out.append([i,i+1])
    return {'equal_length':True,'total_differing_bytes':count,'differing_byte_ranges':out,'range_complete':len(out)<4096}
def sections(x,y):
    return {k:{'before':x['section_hashes'].get(k),'after':y['section_hashes'].get(k)}for k in sorted(x['section_hashes'].keys()|y['section_hashes'].keys())if x['section_hashes'].get(k)!=y['section_hashes'].get(k)}
def read(exe,package,state,arm,tag,rec,n=None):
    args=[str(exe),'--list']if n is None else [str(exe),n,'--exact','--test-threads=1']
    e=env();e.update(INSTA_UPDATE='no',NO_COLOR='1');r=subprocess.run(ns(state,SDK/'bin/cargo',rec,W/'crates'/package)+args,env=e,capture_output=True,timeout=90)
    f=rec/(arm+'-'+tag);f.with_suffix('.stdout').write_bytes(r.stdout);f.with_suffix('.stderr').write_bytes(r.stderr)
    data={'args':args[1:],'exit':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest()}
    if n is None:
        data['names']=[l.rsplit(': ',1)[0]for l in r.stdout.decode().splitlines()if l.endswith(': test')];assert data['names']and r.returncode==0,(package,r.stderr[-450:])
    else:
        text=r.stdout.decode(errors='replace');data.update(stdout=text,stderr=r.stderr.decode(errors='replace')[:800],passed=bool(re.search(r'\b1 passed; 0 failed;',text)),normalized_stdout_sha256=hashlib.sha256(re.sub(rb'finished in [0-9.]+s',b'finished in <elapsed>',r.stdout)).hexdigest())
    return data
root=O/'changed-all-elf-v4';root.mkdir(exist_ok=True);res={}
for mode in ['check','build','test']:
 pp=load(O/mode/'final-v4/first/products-changed-vs-seed.json'); art_rows=load(O/mode/'final-v4/first/artifacts.json');res[mode]={}
 for label,ds in sorted(pp.items()):
    if not (ds.get('before')or{}).get('elf') and not (ds.get('after')or{}).get('elf'):continue
    v=Path(label); caseid=hashlib.sha256(str(v).encode()).hexdigest()[:16];rec=root/(mode+'-'+caseid);rec.mkdir(exist_ok=True)
    if (rec/'result.json').is_file():
        certificate=load(rec/'result.json')
        assert certificate['raw']==[ds['before']['sha256'],ds['after']['sha256']]
        res[mode][str(v.relative_to(D))]=certificate
        continue
    assert not any(rec.iterdir())
    assert ds['before'] and ds['after']; arts=[r for r in art_rows if r.get('exe')==label];test_arts=[r for r in arts if r['profile'].get('test')]; assert len(test_arts)<=1
    states={k:D/'states'/mode/k for k in ['stock-repeat','final-v4']};physical={k:tr(v,st)for k,st in states.items()};xx,yy=[elf(f)for f in physical.values()]
    assert xx['raw']==ds['before']['sha256']and yy['raw']==ds['after']['sha256']
    mask_equal=xx['size']==yy['size'] and xx['content_with_two_wild_fields_masked']==yy['content_with_two_wild_fields_masked']
    dif=sections(xx,yy);rr=raw_ranges(*physical.values())
    case={'raw':[xx['raw'],yy['raw']],'file_sizes':[xx['size'],yy['size']],'all_sections':{'stock':xx['section_hashes'],'retrained':yy['section_hashes']},'section_differences':dif,'build_ids':[xx['gnu_build_id'],yy['gnu_build_id']],'rodata_entsize':[xx['rodata_entsize'],yy['rodata_entsize']],'masked':[xx['content_with_two_wild_fields_masked'],yy['content_with_two_wild_fields_masked']],'only_rodata_entsize_and_gnu_build_id':bool(mask_equal and xx['rodata_entsize']!=yy['rodata_entsize'] and set(dif)=={'.rodata','.note.gnu.build-id'} and xx['section_hashes']['.rodata']['bytes']==yy['section_hashes']['.rodata']['bytes']),'raw_ranges':rr}
    if test_arts:
        src=Path(test_arts[0]['source'])
        assert src.is_relative_to(W/'crates');package=src.relative_to(W/'crates').parts[0]
        ls={k:read(v,package,s,k,'list',rec)for k,s in states.items()};lists=list(ls.values());case['list_results']=ls;case['list_equal']=lists[0]['stdout_sha256']==lists[1]['stdout_sha256']and lists[0]['names']==lists[1]['names']
        common=sorted(set(lists[0]['names'])&set(lists[1]['names']));assert common
        # Predetermined, outcome-independent choice. Only skip if the harness declares a literal ignored test.
        runtime=[]
        for n in common[:3]:
            test={k:read(v,package,s,k,'filter-'+str(len(runtime)),rec,n)for k,s in states.items()};vs=list(test.values());runtime.append({'name':n,'arms':test})
            if all(z['passed']for z in vs)or not all('1 ignored' in z['stdout']for z in vs):break
        case['filter_results']=runtime;case['package']=package
    case['artifact']=v.name;case['is_test_harness']=bool(test_arts);case['case_id']=caseid;res[mode][str(v.relative_to(D))]=case;save(rec/'result.json',case)
    print(mode,v.name,sorted(dif),case['only_rodata_entsize_and_gnu_build_id'],case.get('list_equal'),flush=True)
save(O/'changed-all-elf-v4.json',res)
