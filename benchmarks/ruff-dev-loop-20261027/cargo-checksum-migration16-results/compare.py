"""Fork each admitted stock state, measure old-vs-old and one-time Cargo migration, and test ordinary callers."""
from pathlib import Path
import ast,collections,fcntl,hashlib,json,os,re,runpy,shutil,stat,subprocess,sys
here=Path(__file__).resolve().parent
g=runpy.run_path(here/'runner.py');cd=runpy.run_path(here/'census.py')['census']
H,W,P,D,O,SDK,VERIFIED,FLOOR,ns,proc,translate,save,env,guard,h,hh=[g[k]for k in ('H','W','P','D','O','SDK','VERIFIED','FLOOR','ns','process','translate','save','environment','guard','h','hh')];helper=here/'libcargo_depinfo_b3.so'
load=lambda f:json.loads(f.read_text());L=D/'reader-live';L.mkdir(exist_ok=True)
def manifest(state):
    rows={};seen={};inodes={};outside={};levels={}
    for cur,dirs,names in os.walk(state,followlinks=False):
        dirs.sort();names.sort()
        for name in dirs+names:
            f=Path(cur)/name;s=f.lstat();key=str(f.relative_to(state));mode=stat.S_IMODE(s.st_mode);row=[mode,s.st_mtime_ns]
            if stat.S_ISREG(s.st_mode):
                inode=(s.st_dev,s.st_ino);inodes[key]=inode;seen.setdefault(inode,[]).append(key)
                if inode not in levels:levels[inode]=h(f)
                row=['file',s.st_size,levels[inode],*row];outside[inode]=s.st_nlink
            elif stat.S_ISDIR(s.st_mode):row=['dir',*row]
            elif stat.S_ISLNK(s.st_mode):row=['symlink',os.readlink(f),*row]
            else:raise AssertionError(('non-file source cache entry',key))
            rows[key]=row
    count=collections.Counter();extr=0
    for inode,names in seen.items():
        names.sort();extr+=max(0,outside[inode]-len(names));count[len(names)]+=1
        for name in names:rows[name].append(names[0])
    result=hashlib.sha256()
    for name,row in sorted(rows.items()):result.update(json.dumps([name,row],separators=(',',':')).encode()+b'\n')
    return {'sha256':result.hexdigest(),'entries':len(rows),'files':len(inodes),'hardlink_group_sizes':dict(count),'external_links':extr,'distinct_file_bytes':sum(rows[names[0]][1]for names in seen.values())},inodes
def copy(state,other):
    actual=int(subprocess.check_output(['du','-s','--block-size=1',state],text=True).split()[0]);guard();assert shutil.disk_usage(other.parent).free>FLOOR+actual+3*2**30,(actual,shutil.disk_usage(other.parent).free)
    out=other.parent/(other.name+'-copy.log');err=other.parent/(other.name+'-copy.err')
    assert not other.exists()
    assert g['run'](['cp','-a','--reflink=auto',state,other],os.environ.copy(),out,err)==0
def source_search(mode):
    cold=O/mode/'seed/cold';calls=load(cold/'calls.json')
    for c in calls:
        if c['crate']!='ruff_linter' or c['role']!='rustc-full':continue
        f=cold/('exec.'+str(c['pid'])); assert h(f)==c['raw_file_sha256']
        for l in f.read_text(errors='replace').splitlines():
            m=re.match(r'^execve\("([^"]+)", (\[.*\]), .+ = 0$',l)
            if not m or hh(m[2].encode())!=c['arg_sha256']:continue
            a=ast.literal_eval(m[2]);ext=[a[i+1].split('=',1)[1]for i,v in enumerate(a[:-1])if v=='--extern'and a[i+1].startswith('ruff_python_parser=')];assert len(ext)==1
            dirs=[]
            for i,v in enumerate(a):
                if v=='-L':dirs+=['-L',a[i+1]]
                elif v.startswith('-L')and len(v)>2:dirs.append(v)
            return ext[0],dirs,c['arg_sha256']
    raise AssertionError((mode,'missing real linter argv'))
def exercise(mode,state,img,stage,tag):
    rec=O/mode/stage/(tag+'-readers');rec.mkdir(exist_ok=False)
    opts=ns(state,img,rec);assert opts[-1]=='--';opts=opts[:-1]+['--bind',str(rec),str(L),'--']
    data={};env_=env()
    def execute(label,argv,expected,input_=None):
        rr=subprocess.run(opts+list(map(str,argv)),env=env_,input=input_,capture_output=True,timeout=50);(rec/(label+'.stdout')).write_bytes(rr.stdout);(rec/(label+'.stderr')).write_bytes(rr.stderr)
        data[label]={'args':list(map(str,argv)),'exit':rr.returncode,'stdout_sha':hh(rr.stdout),'stderr_sha':hh(rr.stderr),'stdout':rr.stdout.decode(errors='replace')[:450],'stderr':rr.stderr.decode(errors='replace')[:160]}
        assert rr.returncode==expected,(label,rr.returncode,rr.stderr[-1000:])
        return rr
    if mode=='check':
        md,dirs,caller=source_search(mode);assert translate(Path(md),state).is_file()
        base=['rustc','+ohm','--sysroot',str(SDK),'--crate-type','lib','--crate-name','ordinary_migration_reader','--edition=2024','--emit=metadata','--error-format=json','--extern','ruff_python_parser='+md,*dirs,str(L/'ordinary.rs'),'-o',str(L/'ordinary.rmeta')]
        (rec/'ordinary.rs').write_text('pub fn check_export() { let _ = ruff_python_parser::lexer::lex; }\n');execute('ordinary-success',base,0);data['ordinary-success']['output_hash']=h(rec/'ordinary.rmeta')
        (rec/'ordinary.rs').write_text('pub fn check_export() { let _ = ruff_python_parser::lexer::lex(); }\n');rr=execute('ordinary-error',base,1)
        js=[json.loads(b)for b in rr.stderr.splitlines()if b.startswith(b'{')];errs=[j for j in js if (j.get('code')or{}).get('code')=='E0061'];assert len(errs)==1,js
        sms=[sp for x in errs[0]['children'] for sp in x['spans']if sp['file_name'].endswith('crates/ruff_python_parser/src/lexer.rs') and any('pub fn lex('in c['text']for c in sp['text'])]
        assert len(sms)==1,errs[0]['children']
        data['ordinary-error']['primary']=errs[0]['spans'];data['ordinary-error']['secondary']=sms[0];data['ordinary-error']['error_message']=errs[0]['message'];data['ordinary-error']['metadata_sha']=h(translate(Path(md),state));data['ordinary-error']['source_args']=caller
    else:
        for b in ('ruff','ty'):
            v=D/'target/debug'/b
            assert translate(v,state).is_file(),(mode,'expected ordinary runtime',v)
            execute(b+'-version',[v,'--version'],0)
        z=execute('ruff-F821',[D/'target/debug/ruff','check','--isolated','--output-format','concise','--select','F821','--stdin-filename','input.py','-'],1,b'print(unknown)\n')
        assert b'F821' in z.stdout and b'unknown' in z.stdout
        if mode=='test':
            recs=load(O/mode/stage/tag/'artifacts.json');p=[v['exe']for v in recs if v['name']=='ruff_python_parser'and v['kind']==['lib']and v['profile'].get('test')and v['exe']];assert len(p)==1,p
            z=execute('parser-list',[p[0],'--list'],0);assert b': test' in z.stdout;data['parser-list']['names']=sum(b.endswith(b': test')for b in z.stdout.splitlines())
    save(rec/'result.json',data)
    return data
def compare(mode,action,candidate=None):
    parent=D/'states'/mode/'seed';done=load(O/mode/'seed-complete.json');assert done['receipt']['fresh']==done['receipt']['units']
    state_root=parent.parent;img=SDK/'bin/cargo';seed_census=cd(parent,helper);save(O/mode/'seed-census.json',seed_census)
    if action=='prepare':
        seed_m,inde=manifest(parent);save(O/mode/'seed-tree.json',seed_m)
        for arm in ('stock-repeat','upgraded'):
            q=state_root/arm;copy(parent,q);nm,ino=manifest(q);assert nm['sha256']==seed_m['sha256'] and not any(ino[k]==inode for k,inode in inde.items()),(mode,arm,nm,seed_m)
            nc=cd(q,helper);assert nc==seed_census;save(O/mode/(arm+'-input-tree.json'),nm)
        # Record the original settled outputs/reader through a distinct physical-state run.
        arm='stock-repeat'
    elif action=='candidate':
        assert candidate and len(candidate)==64 and candidate!='34b4d8c96ffb9f6c9c946cbd8475314e0cd4efd53a919a0d643ea978e7556a73'
        q=state_root/'upgraded';img=D/'subjects'/candidate;assert h(img)==candidate;arm='upgraded';nm,_=manifest(q);seed_m=load(O/mode/'seed-tree.json');assert nm['sha256']==seed_m['sha256']
        assert cd(q,helper)==seed_census,mode
    else:raise AssertionError(action)
    q=state_root/arm;old=load(O/mode/'seed'/done['final']/'files.json')
    for tag in ['first','second','third-if-displaced']:
        if tag=='third-if-displaced'and r['fresh']==r['units']and not any(r['physical'].get(k,0)for k in ('rustc-full','rustc-link-only','wild','build-script')):break
        r=proc(mode,arm,tag,q,img);new=load(O/mode/arm/tag/'files.json');changed={k:{'before':old.get(k),'after':new.get(k)}for k in set(old)|set(new)if old.get(k)!=new.get(k)}
        counts=cd(q,helper);save(O/mode/arm/tag/'census.json',counts);save(O/mode/arm/tag/'products-changed-vs-seed.json',changed)
        if arm=='stock-repeat':assert not changed and r['units']==r['fresh'] and not any(r['physical'].get(k,0)for k in ('rustc-full','rustc-link-only','wild','build-script')),(mode,arm,tag,len(changed),r['physical'])
        exercise(mode,q,img,arm,tag)
if __name__=='__main__':
    action=sys.argv[1];assert set(os.sched_getaffinity(0))==set(range(24));g['original']();guard()
    with (P/'native-measure.lock').open('rb')as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        for mode in sys.argv[2:5]:compare(mode,action,sys.argv[5]if len(sys.argv)>5 else None)
    g['original']()
