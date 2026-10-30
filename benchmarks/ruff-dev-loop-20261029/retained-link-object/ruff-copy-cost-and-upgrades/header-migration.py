"""Exercise both opaque incremental-file-format transitions with real Cargo and rustc."""
import ast, collections, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
def read(path): return json.loads(path.read_bytes())
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(f,v):
    with f.open('x') as b:json.dump(v,b,indent=2,sort_keys=True);b.write('\n')
def checked(args,**kw): return subprocess.run(args,check=True,**kw)
def require(y,k):
    if not y:raise RuntimeError(k)
def state(p):
    with p.open('rb') as h:data=h.read(262)
    if data[:4]!=b'RSIC':return None
    return (int.from_bytes(data[4:6],'little'),data[7:7+data[6]].decode())
def paths(base):
    return {str(f):(f.stat().st_ino,f.stat().st_size,*val)
            for directory in (base/'target',base/'shared') for f in directory.rglob('*.bin') if 'incremental' in f.parts and (val:=state(f))}
def delta(lines, prior):
    """Follow successful hardlink/rename inheritance into a compiler's private working dir."""
    proofs=[]; ancestors={k:k for k in prior}
    aliases=[]; opened=[]
    for name,data in lines.items():
        for l in data.splitlines():
            if not re.search(r'\)\s+=\s+(?:0|[1-9][0-9]*)(?:<|$)',l):continue
            if l.startswith(('link(','linkat(','rename(','renameat(','renameat2(')):
                names=[bytes(s,'utf8').decode('unicode_escape') for s in re.findall(r'"([^"]+\.bin)"',l)]
                if len(names)==2:aliases.append(names)
            if l.startswith(('openat(','open(')) and 'O_RDONLY' in l:
                names=re.findall(r'"([^"]+\.bin)"',l)
                if len(names)==1:opened.append((name,names[0]))
    for _ in range(4):
        for a,b in aliases:
            if a in ancestors:ancestors[b]=ancestors[a]
    for proc,path in opened:
        if path in ancestors:
            old=ancestors[path]
            proofs.append(dict(file=Path(path).name,old_ino=prior[old][0],bytes=prior[old][1],
                               header=prior[old][2],stamp=prior[old][3],through_kernel_alias=(old!=path)))
    return proofs

def run_pair(base, first, second, args):
    base.mkdir(mode=0o700); req=base/'project';(req/'src').mkdir(parents=True)
    for n in ('home','bin','cargo-home','target','shared','rustup/toolchains/ohm','logs','bodies','independent'):
        (base/n).mkdir(parents=True,exist_ok=True)
    (base/'cargo-home/config.toml').write_text('[build]\nbuild-dir = '+json.dumps(str(base/'shared'))+'\n')
    (req/'Cargo.toml').write_text('[package]\nname="format_probe"\nversion="0.0.0"\nedition="2024"\n')
    (req/'Cargo.lock').write_text('version = 4\n\n[[package]]\nname = "format_probe"\nversion = "0.0.0"\n')
    for n in ('rustc','cargo'):(base/'bin'/n).symlink_to(args['proxy'])
    def code(v):
        return '#[inline(never)] fn calc<T>(_: T) -> u32 { '+v+' }\nfn main() { println!("{}", calc(7u32)); }\n'
    dirty=[('initial',first,'17','17'),('unchanged-before',first,None,'17'),('switch-unchanged',second,None,'17'),
           ('switch-dirty',second,'29','29'),('switch-dirty-repeat',second,None,'29'),
           ('switch-invalid',second,'UNKNOWN_NATIVE_FORMAT_VALUE',None),
           ('switch-repaired',second,'17','17'),('switch-repaired-repeat',second,None,'17'),
           ('independent-empty17',second,'17','17'),('independent-empty29',second,'29','29')]
    rows={}; vv={}
    def env_for(arm):
        b=['bwrap','--die-with-parent','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc',
           '--bind',str(base),str(base),'--ro-bind',args['kits'][arm],str(base/'rustup/toolchains/ohm'),
           '--ro-bind',args['cargo'],str(base/'rustup/toolchains/ohm/bin/cargo'),'--clearenv']
        for k,v in dict(HOME=str(base/'home'),USER='replay',LOGNAME='replay',CARGO_HOME=str(base/'cargo-home'),
                        CARGO_TARGET_DIR=str(base/'target'),RUSTUP_HOME=str(base/'rustup'),PATH=str(base/'bin')+':/usr/bin:/bin',
                        CARGO_NET_OFFLINE='true',CARGO_CACHE_AUTO_CLEAN_FREQUENCY='never',RUSTUP_AUTO_INSTALL='0',LC_ALL='C.UTF-8',TZ='UTC').items():b+=['--setenv',k,v]
        return b+['--chdir',str(req),'--']
    for arm in (first,second):
        z=checked(env_for(arm)+['rustc','+ohm','-vV'],capture_output=True)
        vv[arm]=z.stdout.decode()
    require(vv[first]==vv[second],"different apparent rustc version")
    for nm,arm,want,answer in dirty:
        require(shutil.disk_usage(base).free>48*2**30 and shutil.disk_usage(Path.home()).free>48*2**30 and int([x.split()[1]for x in Path('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:')][0])*1024>32*2**30,'reserve')
        if nm.startswith('independent-empty'):
            for n in ('shared','target'):
                x=base/n;x.rename(base/'independent'/(nm+'-'+n));x.mkdir()
        if want is not None:(req/'src/main.rs').write_text(code(want))
        before=paths(base)
        tr=base/'logs'/nm;tr.mkdir(); (tr/'raw').mkdir()
        cmd=env_for(arm)+['strace','-ff','-qq','-yy','-s','131072','-e','trace=execve,link,linkat,rename,renameat,renameat2,open,openat','-o',str(tr/'raw/exec'),
                          'cargo','+ohm','build','--locked','--offline','-j2','--message-format=json']
        with (tr/'stdout').open('xb')as so,(tr/'stderr').open('xb')as se:
            proc=subprocess.run(cmd,stdout=so,stderr=se)
        so=(tr/'stdout').read_bytes(); se=(tr/'stderr').read_bytes()
        require(proc.returncode==(0 if answer is not None else 101),(nm,proc.returncode,se[-1200:]))
        typed=[json.loads(l) for l in so.splitlines()]
        require(typed[-1]=={'reason':'build-finished','success':answer is not None},'Cargo typed finish')
        files={p.name:p.read_text()for p in (tr/'raw').glob('exec.*')};actual=[];links=0
        for p,ls in files.items():
            for line in ls.splitlines():
                if not line.startswith('execve(') or not line.endswith(' = 0'):continue
                m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[\da-f]+ /\* [^*]* \*/|NULL)\)\s+= 0',line)
                require(m,line[:120]);ex=ast.literal_eval(m[1]);av=ast.literal_eval(m[2])
                if ex==str(base/'rustup/toolchains/ohm/bin/rustc') and '--crate-name'in av and '--out-dir'in av:
                    require(av[av.index('--crate-name')+1]=='format_probe' and any('incremental='in x for x in av),'actual incremental compiler')
                    actual.append((p,av))
                if ex.endswith('/wild-ld/ld.bfd') and '-o' in av:links+=1
        full=len(actual);after=paths(base)
        if nm not in ('switch-unchanged','unchanged-before','switch-dirty-repeat','switch-repaired-repeat'):
            require(full==1,(nm,full))
        if nm in ('unchanged-before','switch-dirty-repeat','switch-repaired-repeat'): require(full==links==0,(nm,full,links))
        if answer is not None:
            exe=base/'target/debug/format_probe'; value=checked([exe],capture_output=True).stdout.decode().strip();require(value==answer,(nm,value,answer))
            elt=sha(exe); dest=base/'bodies'/elt
            if not dest.exists():shutil.copyfile(exe,dest)
            require(sha(dest)==elt,'complete ELF')
        else:
            require(b'E0425'in so and b'UNKNOWN_NATIVE_FORMAT_VALUE'in so and not (b'panicked' in se or b'internal compiler error' in se),'true invalid source')
            value=None;elt=None
        if nm in ('initial','switch-dirty','switch-repaired','independent-empty17','independent-empty29'):
            require(any(v[2]==args['formats'][arm]for v in after.values()),(nm,'missing expected header',after))
        # Link/rename can be performed by a sibling worker; constrain the final open to the real selected rustc or any of its traced threads.
        real_inputs=delta(files,before)
        rec={'status':proc.returncode,'value':value,'elf':elt,'full':full,'stock_wild':links,'old_headers':sorted({(v[2],v[3])for v in before.values()}),
             'new_headers':sorted({(v[2],v[3])for v in after.values()}),'opened_old':real_inputs,
             'original_argv_sha256':[hashlib.sha256(b'\0'.join(x.encode()for x in a)+b'\0').hexdigest()for p,a in actual],
             'source_sha256':sha(req/'src/main.rs'),'raw_tree':hashlib.sha256(json.dumps({n:hashlib.sha256(v.encode()).hexdigest()for n,v in files.items()},sort_keys=True).encode()).hexdigest()}
        save(tr/'phase.json',rec); rows[nm]=rec
    old=args['formats'][first];new=args['formats'][second]
    frontier=[(nm,r)for nm,r in rows.items() if nm in ('switch-unchanged','switch-dirty') and r['full']]
    require(any(v['header']==old for nm,r in frontier for v in r['opened_old']),('no real read of older version in first dirty compiler', [(k,v['old_headers'],v['opened_old'])for k,v in frontier]))
    for k,e in [('initial','independent-empty17'),('switch-unchanged','independent-empty17'),('switch-repaired','independent-empty17'),('switch-dirty','independent-empty29')]:
        require(rows[k]['elf']==rows[e]['elf'],(k,'complete program mismatch'))
    require(any(v[0]==old for v in rows['initial']['new_headers'])and any(v[0]==new for v in rows['switch-dirty']['new_headers']),'header transition')
    return {'first':first,'second':second,'shared_vV':vv[first],'phases':rows}
def main():
    args=read(Path(sys.argv[1]));base=Path(args['work']);require(not base.exists(),'fresh root');base.mkdir(mode=0o700)
    p,q=args['order']; results={}
    require(sha(Path(args['cargo']))==args['cargo_sha256'],'physical Cargo')
    physical={}
    for role,folder in args['kits'].items():
        kit=Path(folder); driver,=kit.glob('lib/librustc_driver*.so'); physical[role]={'driver':sha(driver),'rustc':sha(kit/'bin/rustc'),'wild':sha(kit/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')}
        require(physical[role]['driver']==args['drivers'][role] and physical[role]['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5','physically authenticated tools')
    require(physical[p]['rustc']==physical[q]['rustc'],'same rustc frontend');save(base/'physical-tools.json',physical)
    for first,second in ((p,q),(q,p)):
        result=run_pair(base/(first+'-'+second),first,second,args);results[first+'-'+second]=result;save(base/(first+'-'+second+'.json'),result)
    save(base/'terminal.json',results)
    print(sha(base/'terminal.json'))
if __name__=='__main__':main()
