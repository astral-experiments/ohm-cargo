"""Re-derive producer lineage, true incoming operands and compiler process/output counts from actual host records."""
from pathlib import Path
import ast,collections,functools,gzip,hashlib,json,re,subprocess,sys
O=Path.home()/'.cache';host=O/'ohm-ron-fixed-whole-native-h4-20261028-v1';proto=O/'ohm-noquery-full-native-h4-20261028-v2/protocol'
sys.path.insert(0,str(proto));import engine as q
h=lambda b:hashlib.sha256(b).hexdigest()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(a):return h(json.dumps(a,sort_keys=True,separators=(',',':')).encode())
def read(p):return json.loads(p.read_bytes())
def dump(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
trace_re=re.compile(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)')
sobj=read(proto/'subject-binding.json')
libid='libron-f3d684a377188226'
def header(p,driver):
    exe=str(q.FROZEN/'bin/rustc');run=subprocess.run(['bwrap','--ro-bind','/','/','--ro-bind',str(driver),str(q.FROZEN/'lib'/q.SONAME),'--',exe,'--sysroot',str(q.FROZEN),'-Zls=all',p],capture_output=True,check=True)
    z=re.search(rb'^private hash ([0-9a-f]+) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]+)',run.stdout,re.M);assert z
    return {'private_hash':z[1].decode(),'stable_crate_id':z[2].decode(),'public_hash':z[3].decode(),'textually_reported_all_crate_metadata_sha256':h(run.stdout),'stderr':h(run.stderr)}
def vary(a,b):
    a=a.read_bytes();b=b.read_bytes();rs=[];diff=0
    for n,(x,y) in enumerate(zip(a,b)):
        if x!=y:
            diff+=1
            if rs and rs[-1][1]==n:rs[-1][1]+=1
            else:rs.append([n,n+1])
    return {'old_sha256':h(a),'new_sha256':h(b),'old_bytes':len(a),'new_bytes':len(b),'changed_bytes_in_common_length':diff,'trailing_byte_delta':len(b)-len(a),'range_count':len(rs),'first_ranges':rs[:12],'last_ranges':rs[-4:]}
def phase(folder,pre,previous=None):
    raw=read(folder/'native-processes.json');snap=read(folder/'native-elf.json');trace=folder/'trace';exe,=set(z[-1] for z in raw['linkers'] if z[1]);assert sha(Path(exe))=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    terminal={};flags=[];jobs=[];ros=folder/'ron';meta,=ros.glob('libron-*.rmeta');rlib=meta.with_suffix('.rlib')
    for pid,name,mode,exitcode,sig in raw['jobs']:
        assert exitcode==0
        jobs.append([pid,name,mode,sig])
        if name=='ron':
            f=trace/('exec.'+str(pid));line,=[l for l in f.read_bytes().splitlines() if b'"--crate-name", "ron"' in l and re.search(rb'\)\s+= 0$',l)]
            m=trace_re.search(line);a=ast.literal_eval(m[2].decode());flags.append({'pid':pid,'args':digest(a),'raw':h(line),'binary_depdepinfo':'-Zbinary-dep-depinfo' in a,'explicit_checksum':'-Zchecksum-hash-algorithm=blake3' in a,'ordered_rust_input_positions':[(i,Path(a[i+1].split('=',1)[1]).name)for i,x in enumerate(a)if x=='--extern']})
    for pid,packaged,output,code,sig,linker in raw['linkers']:
        if not packaged:continue
        assert code==0
        src=trace/('exec.'+str(pid));ls=[]
        for l in src.read_bytes().splitlines():
            if b'/ld.bfd",' in l and re.search(rb'\)\s+= 0$',l):
                m=trace_re.search(l);a=ast.literal_eval(m[2].decode());ls.append((l,a))
        assert len(ls)==1;l,a=ls[0];assert a[a.index('-o')+1]==output
        dest=Path(output).name
        rr=[(i,Path(x).name)for i,x in enumerate(a)if Path(x).name==rlib.name];meta_args=[(i,Path(x).name)for i,x in enumerate(a)if x.endswith('.rmeta')]
        k=str(pid) if pre=='cold' else dest
        assert k not in terminal
        terminal[k]={'pid':pid,'destination':dest,'raw_execve_sha256':h(l),'argv':digest(a),'ron_archive':rr,'standalone_rmeta':meta_args,'other_rust_archive_count':sum(x.endswith('.rlib') for x in a)-len(rr),'literal_response_files':sum(x.startswith('@') for x in a)}
    calls=[json.loads(l)for l in(folder/'stdout').read_bytes().splitlines()];rows=[r for r in calls if r.get('reason')=='compiler-artifact'];assert len(rows)==619 and calls[-1]=={'reason':'build-finished','success':True}
    products=read(folder/'ron-members.json');numeric=collections.Counter(v['profile']['test']for v in rows if v['executable']);assert numeric=={True:84,False:18}
    actual=read(folder/'record.json') if (folder/'record.json').exists() else None
    if actual:assert actual['counts']==raw['counts'] and actual['actual_elfs']==len(snap)==110 and actual['elapsed_ns'] is None
    else:assert read(folder/'status.json')=={'rc':0,'elapsed_ns':None}
    pubs=read(ros/'lib-ron.public-api-hash')
    x={'units':len(rows),'fresh':sum(r['fresh'] for r in rows),'program_files':len(snap),'profile_executable':{'test':numeric[True],'normal':numeric[False]},'native_outputs':{str(Path(k).relative_to(q.TARGET)):v for k,v in snap.items()},'stdout_sha256':sha(folder/'stdout'),'stderr_sha256':sha(folder/'stderr'),'native_parse_sha256':sha(folder/'native-processes.json'),'mode_counts':raw['counts'],'rustc_jobs':jobs,'wild_jobs':terminal,'actual_ron':flags,'archive':sha(rlib),'metadata':sha(meta),'root':header(meta,sobj['old_driver']['path']),'cargo_public_api':pubs,'ar_members':products,'depfile':sha(next(ros.glob('ron-*.d'))),'fingerprint':sha(ros/'dep-lib-ron'),'foreign_marker':b'ohm-foreign-span-bytes' in next(ros.glob('ron-*.d')).read_bytes(),'raw_trace_count':len(list(trace.glob('exec.*'))),'raw_trace_set':digest({f.name:sha(f)for f in sorted(trace.glob('exec.*'))}),'reader':actual['reader']if actual else None,'cargo_roster':actual['roster']if actual else None,'diagnostics':actual['diagnostics']if actual else None}
    if previous:x['previous_full_metadata_byte_delta']=vary(next((previous/'ron').glob('libron-*.rmeta')),meta)
    return x
def main():
    d=host/'results/fixed-release-rust';seq=['cold','unchanged-1','unchanged-2','unchanged-3'];assert(host/'rc').read_text().strip()=='0'
    last=None;r={}
    for label in seq:
        r[label]=phase(d/label,label,last);last=d/label
    # The second historical release used separately held inputs; no equivalence across these arms is assumed.
    z=O/'ohm-ron-identical-inputs-h4-20261028-v1';assert (z/'rc').read_text().strip()=='0'
    products={n:read(z/n/'products.json')for n in ('normal1','normal2','explicit1','explicit2','normal3')};products['donor']=read(z/'donor.json')
    ref={'inputs':read(z/'inputs.json'),'summary':read(z/'complete.json'),'products':products,'normal1_to_2':vary(next((z/'normal1/out').glob('*.rmeta')),next((z/'normal2/out').glob('*.rmeta')))}
    for n in ('normal1','normal2','normal3','explicit1','explicit2'):ref.setdefault('headers',{})[n]=header(next((z/n/'out').glob('*.rmeta')),sobj['new_driver']['path'])
    out={'command':q.PLAN['command'],'ruff':'93526150df078af7dd8fc4226cdcc469539d2001','cargo':'0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322','rustc':sobj['old_driver']['sha256'],'replay_rustc':sobj['new_driver']['sha256'],'default_trust':True,'zero_clocks':True,'primary':r,'captured_compiler_replay':ref}
    sys.stdout.buffer.write(gzip.compress(dump(out),mtime=0))
main()
