#!/usr/bin/env python3
"""Perform one real, independently empty full-Ruff storage history on a user-supplied Linux output tmpfs."""
import argparse,gzip,hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
A='b5dba861cc38e3f7fb4524c9ceba3e01a474ea13'
B='7b13f01ba1569887a25670820764b24c206da8e5'
SOURCE='08d49cba6aacb0cac27a96eea335ed1c7439f483'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_bytes())
def store(p,row):p.write_text(json.dumps(row,indent=2,sort_keys=True)+'\n')
def module(name,script):
    spec=importlib.util.spec_from_file_location(name,HERE/script);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
class OutputView:
    def __init__(self,path):self.root=path
    def __truediv__(self,key):return self.root if key=='.allocation' else self.root/key
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--git-source',required=True,type=Path,help='read-only local Ruff Git clone containing both historic commits')
    p.add_argument('--work',required=True,type=Path,help='a new private working directory, then reuse the same one for later installations')
    p.add_argument('--output-tmpfs',required=True,type=Path,help='same exclusive Linux tmpfs mountpoint, containing only two empty owned directories, products and shared')
    p.add_argument('--product',type=Path,help='optional source-build product.json from the enrolled Rust revision, verified against all 55 SDK members')
    p.add_argument('--case',required=True,choices=['off-storage','on-storage','off-clean-B','on-clean-B'])
    args=p.parse_args();work=args.work.resolve();out=args.output_tmpfs.resolve(strict=True);git_source=args.git_source.resolve(strict=True)
    if not (out.is_dir() and os.path.ismount(out) and set(q.name for q in out.iterdir())=={'products','shared'} and subprocess.check_output(['findmnt','-rn','-o','FSTYPE','-T',out],text=True).strip()=='tmpfs'):p.error('supply an exclusive output tmpfs with products/ and shared/')
    for q in (out/'products',out/'shared'):
        if q.is_symlink() or not q.is_dir() or q.stat().st_uid!=os.getuid() or q.stat().st_dev!=out.stat().st_dev or any(q.iterdir()):p.error('each installation needs two empty, owned output directories')
    if any(os.environ.get(k) for k in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER')):p.error('start with no Rust compiler, wrapper or extra flag overrides')
    if out==work or out in work.parents or work in git_source.parents or git_source in work.parents or git_source==work:p.error('scratch, immutable source and output must be separate')
    env={**os.environ,'RUSTUP_AUTO_INSTALL':'0','CARGO_NET_OFFLINE':'true','LC_ALL':'C','LANG':'C'}
    if not work.exists():work.mkdir(mode=0o700,parents=False)
    marker=work/'replication.json';src=work/'src'
    def git(*argv,out=False):return subprocess.run(['git','--no-optional-locks','-C',src,*argv],env=env,check=True,capture_output=out).stdout
    if not marker.exists():
        if any(work.iterdir()):p.error('first execution requires a new empty work directory')
        subprocess.run(['git','clone','--no-checkout','--no-hardlinks','--no-tags',git_source,src],env=env,check=True)
        for label,rev in [('historical-parent',A),('historical-feature',B)]:
            found=subprocess.run(['git','--no-optional-locks','-C',src,'show-ref','--verify','--quiet','refs/heads/'+label])
            if found.returncode==1:git('branch',label,rev)
            else:assert found.returncode==0 and git('rev-parse','refs/heads/'+label,out=True).decode().strip()==rev
        store(marker,{'schema':1,'source':str(git_source),'work':str(work),'mount':str(out),'Ruff':[A,B]})
    else:
        assert read(marker)=={'schema':1,'source':str(git_source),'work':str(work),'mount':str(out),'Ruff':[A,B]}
        assert not git('status','--porcelain','--untracked-files=normal',out=True),'unexpected change in private source'
    assert work.stat().st_dev!=out.stat().st_dev and git('rev-parse','historical-parent',out=True).decode().strip()==A and git('rev-parse','historical-feature',out=True).decode().strip()==B
    get=lambda argv:Path(subprocess.check_output(argv,env=env,text=True).strip())
    cc=get(['rustup','which','--toolchain','ohm','rustc']);cargo=get(['rustup','which','--toolchain','ohm','cargo'])
    sdk=get(['rustc','+ohm','--print','sysroot']);wild=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    drivers=sorted((sdk/'lib').glob('librustc_driver-*.so'));assert drivers and wild.is_file()
    assert cc.samefile(sdk/'bin/rustc') and cargo.samefile(sdk/'bin/cargo')
    tools={'bin/rustc':sha(cc),'bin/cargo':sha(cargo),**{str(q.relative_to(sdk)):sha(q) for q in [wild,*drivers]}};product=None
    if args.product:
        product=read(args.product);assert product['rust']==SOURCE and len(product['native_files'])==55
        assert {k:sha(sdk/k) for k in product['native_files']}==product['native_files']
    identity={'sdk':str(sdk),'tools':tools,'source_product_checked':sha(args.product) if args.product else None}
    if (work/'sdk.json').exists():assert read(work/'sdk.json')==identity
    else:store(work/'sdk.json',identity)
    installation=work/args.case;installation.mkdir(mode=0o700)
    mode=args.case.split('-')[0];sequence=[('empty-A',A),('first-B',B),('return-A',A),('return-B',B),('unchanged-B',B)] if args.case.endswith('storage') else [('empty-B',B)]
    oracle=module('cli_oracle','cli-controls.py');meter=module('class_observer','meter.py');observed={}
    for phase,rev in sequence:
        git('switch','--quiet','historical-parent' if rev==A else 'historical-feature')
        assert git('rev-parse','HEAD',out=True).decode().strip()==rev
        visit=installation/phase
        subprocess.run([sys.executable,'-IB',HERE/'measure.py','--mount',out,'--save',visit,'--source',src,'--cache',mode],env=env,check=True)
        after=read(visit/'after.json');rows,ledger=meter.scan(OutputView(out),after);assert (rows,ledger)==meter.scan(OutputView(out),after)
        cats=meter.summarize(rows);assert cats['slices']['all']==after['all']['allocated_bytes']
        store(visit/'file-classes.json',cats)
        with gzip.open(visit/'files.jsonl.gz','wt',encoding='utf-8',compresslevel=3) as f:
            for row in rows:f.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
        stream=[json.loads(v) for v in (visit/'cargo.stdout').read_bytes().splitlines()]
        arts=[v for v in stream if v.get('reason')=='compiler-artifact'];assert len(arts)==375 and stream[-1]=={'reason':'build-finished','success':True}
        bins=[Path(v['executable']) for v in arts if v['target']['name']=='ruff' and 'bin' in v['target']['kind'] and v['executable']]
        assert len(bins)==1 and bins[0].samefile(out/'products/debug/ruff')
        verdict=oracle.cli_checks(visit,bins[0],env,src,rev)
        argv=['rustc','+ohm','--edition=2024','--crate-name','ohm_branch_reader',str(HERE/'consumer.rs')]
        for crate in ('ruff_python_ast','ruff_python_parser'):
            options={f for v in arts if v['target']['name']==crate and 'lib' in v['target']['kind'] for f in v['filenames'] if f.endswith('.rlib')};assert len(options)==1
            argv+=['--extern',crate+'='+options.pop()]
        paths={str(f.parent) for base in ('products','shared') for pat in ('*.rlib','*.so') for f in (out/base).rglob(pat)}
        for path in sorted(paths):argv+=['-L','dependency='+path]
        for path in sorted({v['out_dir'] for v in stream if v.get('reason')=='build-script-executed' and v.get('out_dir')}):argv+=['-L','native='+path]
        reader=work/'reader.elf';argv+=['-o',str(reader)]
        with (visit/'reader-compile.stderr').open('xb') as err:subprocess.run(argv,env=env,cwd=src,stderr=err,check=True)
        stdout=subprocess.check_output([reader],env=env,cwd=src);assert stdout.strip()==(b'Expr=64 valid=1 rejected' if rev==A else b'Expr=56 valid=1 rejected')
        now={'source':rev,'cli':sha(bins[0]),'reader':sha(reader),'reader_stdout':stdout.decode().strip(),'verdicts':verdict}
        if rev in observed:assert observed[rev]==now
        observed[rev]=now
        store(visit/'native.json',now)
    store(installation/'completed.json',observed)
    other=work/(mode+'-clean-B' if args.case.endswith('storage') else mode+'-storage')/'completed.json'
    if other.is_file():assert observed[B]==read(other)[B]
    print(json.dumps({'case':args.case,'real_rust_product_files_verified':len(product['native_files']) if product else 0,'typed_per_visit':375,'source_rows':len(sequence),'matched_other_B':other.is_file(),'complete_elfs':{k:v['cli'] for k,v in observed.items()}},indent=2))
if __name__=='__main__':main()
