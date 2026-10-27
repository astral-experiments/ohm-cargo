from pathlib import Path
import collections,hashlib,json,os,shutil,subprocess,sys,time
d=Path(__file__).resolve().parents[2];n=Path('/home/dev-user/.cache/ohm-ruff-packed-edges-20261026/nonleaf');sr=n/'trait-pgo-state';rt=sr/'sysroot';drivername='librustc_driver-774a793a844d5500.so';arm,phase=sys.argv[1:3];assert arm in ('control','candidate')
driver=(sr/'armB' if arm=='control' else d/'stage2-candidate')/drivername
assert driver.is_file()
work=Path('/dev/shm/ohm-native-history-20261027');work.mkdir(exist_ok=True);route=work/'active';route.mkdir(exist_ok=True);assert not any(route.iterdir());seed=work/(arm+'-seed')
src=Path('/home/dev-user/code/oss/ruff-ohm-native-parser-holdout-20261027');git=['git','--no-optional-locks','-C',str(src)];parent='3bb0dac23569fb607e781ca8e401c6eba71b14dd';child='c1eaf6ff72875a68e2585d50deaff220ea1d8ce9';assert subprocess.check_output(git+['rev-parse','HEAD']).decode().strip()==parent and not subprocess.check_output(git+['status','--porcelain'])
out=d/'historical-confirmation-v3-raw';out.mkdir(exist_ok=True);edits=[*subprocess.check_output(git+['diff','--name-only',parent,child]).decode().splitlines()];assert len(edits)==3
altered=work/'child'
if not altered.exists():
    subprocess.run(['cp','-a',src,altered],check=True)
    subprocess.run(['git','apply','--check',d/'holdout.patch'],cwd=altered,check=True);subprocess.run(['git','apply',d/'holdout.patch'],cwd=altered,check=True)
for f in edits:assert (altered/f).read_bytes()==subprocess.check_output(git+['show',child+':'+f])
wrap=out/'rustc-recorder';body='''#!/bin/sh
printf '%s\\0' "$@" > "$REC/rustc.$$.argv"
exec "$@"
'''
if not wrap.exists():wrap.write_text(body);wrap.chmod(0o755)
def sha(f):
    with f.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
def run(store,source,mode,tag):
    rec=out/(arm+'-'+tag+'-'+mode);rec.mkdir()
    home=store/'home';home.mkdir(exist_ok=True)
    for what in ('registry','git'):
        if not (home/what).exists():(home/what).symlink_to(d/'holdout-cargo-home'/what)
    cmd=['taskset','-c','20-23','bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(store),str(route),'--bind',str(rec),str(rec),'--ro-bind',str(source),str(src),'--ro-bind',str(n/'cargo-native'),str(rt/'bin/cargo'),'--ro-bind',str(driver),str(rt/'lib'/drivername),'--chdir',str(src),'--','/home/dev-user/.cargo/bin/cargo','+ohm',mode,'--locked','--offline','-p','ruff_python_formatter','--message-format=json']
    if mode=='test':cmd.append('--no-run')
    env=dict(os.environ,RUSTUP_HOME=str(sr/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTUP_TOOLCHAIN='ohm',CARGO_HOME=str(route/'home'),CARGO_TARGET_DIR=str(route/'target'),CARGO_BUILD_BUILD_DIR=str(route/'shared'),CARGO_BUILD_JOBS='4',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',RUSTC_WRAPPER=str(wrap),REC=str(rec),GIT_OPTIONAL_LOCKS='0')
    t=time.monotonic_ns()
    with (rec/'stdout').open('xb') as o,(rec/'stderr').open('xb') as e:returncode=subprocess.run(cmd,env=env,stdout=o,stderr=e).returncode
    elapsed=time.monotonic_ns()-t;art=[];diags=[]
    for l in (rec/'stdout').read_bytes().splitlines():
        j=json.loads(l)
        if j['reason']=='compiler-artifact':art.append(j)
        if j['reason']=='compiler-message':diags.append(j)
    if returncode:raise RuntimeError((rec,returncode,(rec/'stderr').read_text()[-800:],[(j['message']['message']) for j in diags if j['message']['level']=='error'][-4:]))
    products={str(Path(a['executable']).relative_to(route)):sha(store/Path(a['executable']).relative_to(route)) for a in art if a['executable']}
    import struct,mmap
    sections={}
    for f in products:
        elf=store/f
        with elf.open('rb') as fd, mmap.mmap(fd.fileno(),0,access=mmap.ACCESS_READ) as m:
            assert m[:6]==b'\x7fELF\x02\x01'
            offset,=struct.unpack_from('<Q',m,40)
            stride,count,string_index=struct.unpack_from('<HHH',m,58)
            defs=[struct.unpack_from('<IIQQQQIIQQ',m,offset+stride*i) for i in range(count)]
            names=m[defs[string_index][4]:defs[string_index][4]+defs[string_index][5]]
            sections[f]={names[k:names.find(b'\0',k)].decode():{'bytes':n,'hash':hashlib.sha256(m[o:o+n]).hexdigest()} for k,t,flags,addr,o,n,link,info,align,entry in defs if t!=8 and n}
    import sys,re
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from symbols import decompose
    bank=json.loads((Path(__file__).resolve().parent/'parent-symbol-bank.json').read_bytes())[mode]
    symbol_digests={}
    for f in products:
        name=Path(f).name;summary,symbols=decompose(store/f);cfg=bank[name]
        if source==altered:
            allowed={tuple(x) for x in cfg['volatile_hidden_keys']};stable=[]
            for t in symbols:
                item=t;match=re.fullmatch(r'(.+)\.llvm\.([0-9]+)',t[0])
                if match and t[2]==2 and (match[1],*t[1:]) in allowed:
                    item=[match[1]+'.llvm.<validated-private-label>',*t[1:]]
                stable.append(item)
            enc=lambda x:json.dumps(x,separators=(',',':'),ensure_ascii=False)
            summary['structural_sha256']=hashlib.sha256(enc(sorted(stable,key=enc)).encode()).hexdigest()
            assert summary['structural_sha256']==cfg['invariant_sha256'] and summary['symbols']==cfg['symbol_count'],(arm,tag,name,summary)
        else:
            assert summary['sorted_sha256']==cfg[arm+'_fresh_full_names'],(arm,tag,name,summary)
        symbol_digests[name]=summary
    (rec/'elf-symbols.json').write_text(json.dumps(symbol_digests,sort_keys=True)+'\n')
    (rec/'elf-sections.json').write_text(json.dumps(sections,sort_keys=True)+'\n')
    executable=next((store/f for f in products if f=='target/debug/ruff_python_formatter'), None)
    samples={}
    if executable:
        for text in ('raise from exc\n','raise from None\n','x=1\n','raise ValueError from exc\n'):
            q=subprocess.run([str(executable)],input=text.encode(),capture_output=True)
            samples[text]=[q.returncode,q.stdout.decode(),q.stderr.decode()]
        (rec/'semantic.json').write_text(json.dumps(samples,indent=2)+'\n')
    api={}
    for p in store.rglob('lib-ruff_python_parser.public-api-hash'):api[str(p.relative_to(store))]=p.read_text().strip()
    commands=[]
    for f in rec.glob('rustc.*.argv'):
        args=[x.decode() for x in f.read_bytes().split(b'\0') if x]
        name=args[args.index('--crate-name')+1] if '--crate-name' in args else None
        if name!='___' and (name or any(a in ('link-only','-Zlink-only') for a in args)):commands.append([name,any(a in ('-Zlink-only','link-only') for a in args),f.name])
    dirty=[(a['target']['name'],a['target']['kind']) for a in art if not a['fresh']];res=dict(command=cmd[-8:],arm=arm,phase=tag,mode=mode,compiler=sha(driver),base=parent,edit=child,patch_sha256=sha(d/'holdout.patch'),source=str(source),units=len(art),rustcs=sorted(commands,key=str),dirty=sorted(dirty),executables=products,parser_api=api,elapsed_ns=elapsed,diagnostics=diags)
    (rec/'receipt.json').write_text(json.dumps(res,indent=2)+'\n');print(tag,mode,'units',len(art),'rustcs',[(x,y) for x,y,z in commands],f'{elapsed/1e9:.4f}s','executables',len(products),'API',list(api.values()),flush=True);return res
