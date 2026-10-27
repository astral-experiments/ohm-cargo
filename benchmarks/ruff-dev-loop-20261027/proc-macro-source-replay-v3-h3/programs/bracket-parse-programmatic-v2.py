"""Localize a remaining metadata encoding difference on the combined green/red macro specimen."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027'); F=P/'frozen-toolchain'
X=Path.home()/'.cache/ohm-233-position-qualified-20261027';S=X/'mixed-registry-seed-programs-20261027'
original=S/'rmake-incremental-proc-macro-source-tracked-final/fixture'
out=P/'mixed-registry-only-pilot'/('bracket-parsed-source-'+sys.argv[2]);out.mkdir(mode=0o700);logical=P/'parse-bracket-both-compilers-logical';logical.mkdir(mode=0o700,exist_ok=True);assert not any(logical.iterdir())
image=Path(sys.argv[1]); cfg=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',RUSTC_BOOTSTRAP='1')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def run(st,tag,args):
    d=st.parent/tag;d.mkdir();n=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(out),str(out),'--bind',str(st),str(logical),'--ro-bind',str(image),str(F/'lib/librustc_driver-774a793a844d5500.so'),'--chdir',str(logical),'--','rustc','+ohm','--edition=2024',*args]
    r=subprocess.run(n,env=cfg,capture_output=True);(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
    dump(d/'argv.json',n);assert not r.returncode,(tag,r.stderr[-1200:]);return d
r={}
for variety in ['programmatic','programmatic-stats','programmatic-always-run','original-same-path']:
    a=out/variety;a.mkdir();st=a/'source';shutil.copytree(original,st)
    maker=(st/'maker.rs').read_text();unit=(st/'producer.rs').read_text()
    if variety.startswith('programmatic'):
        maker='#![feature(proc_macro_tracked_path)]\nextern crate proc_macro;\nuse proc_macro::{Ident, Literal, Punct, Spacing, Span, TokenStream, TokenTree};\nfn constant(name: &str, value: u32) -> TokenStream {\n let ident = |s| TokenTree::Ident(Ident::new(s, Span::call_site()));\n let punct = |c| TokenTree::Punct(Punct::new(c, Spacing::Alone));\n [ident("pub"), ident("const"), ident(name), punct(\':\'), ident("u32"), punct(\'=\'), TokenTree::Literal(Literal::u32_unsuffixed(value)), punct(\';\')].into_iter().collect()\n}\n#[proc_macro_attribute]\npub fn parsed(_:TokenStream, item:TokenStream)->TokenStream { eprintln!("executed attribute"); item }\n#[proc_macro_derive(Parsed)]\npub fn parsed_derive(_:TokenStream)->TokenStream { eprintln!("executed derive"); constant("DERIVED_LINE",4) }\n#[proc_macro_derive(Tracked)]\npub fn tracked(_:TokenStream)->TokenStream {\n eprintln!("executed tracked derive");\n let path = "parse-input.txt";\n let number: u32 = std::fs::read_to_string(path).unwrap().parse().unwrap();\n proc_macro::tracked::path(path); constant("TRACKED",number)\n}\n#[proc_macro]\npub fn position(token:TokenStream)->TokenStream {\n let span=token.into_iter().next().unwrap().span();\n TokenTree::Literal(Literal::string(&format!("{span:?}"))).into()\n}\n'
    if variety=='programmatic-always-run':
        for label in ['executed attribute','executed derive']:
            line='eprintln!("'+label+'");';maker=maker.replace(line,line+' proc_macro::tracked::path("constant.txt");')
        (st/'constant.txt').write_text('fixed')
    if variety=='only-tracked':
        unit=unit.replace('#[maker::parsed]\n','').replace('maker::Parsed, maker::Tracked','maker::Tracked')
    if variety=='only-cached':unit=unit.replace('maker::Parsed, maker::Tracked','maker::Parsed')
    if variety=='literal-const':maker=maker.replace('= line!();','= 4;')
    (st/'maker.rs').write_text(maker);run(st,'plugin',['--crate-type=proc-macro','maker.rs','-o','libmaker.so'])
    group={}
    for state,num,asset,inc in [('train',7,'91','retained'),('warm',8,'379','retained'),('clean',8,'379','empty'),('clean-repeat',8,'379','empty-repeat')]:
        (st/'producer.rs').write_text(unit.replace('    7',f'    {num}'));(st/'parse-input.txt').write_text(asset)
        flags=['-Zcache-proc-macros='+('no' if variety=='cache-off' else 'yes'),'-Zpublic-api-hash='+('no' if variety=='ordinary-metadata' else 'yes')]
        if variety=='programmatic-stats':flags+=['-Zmeta-stats']
        d=run(st,state,['producer.rs','--extern','maker=libmaker.so','-Cincremental='+inc,*flags,'--emit=link,metadata'])
        shutil.copyfile(st/'libproducer.rmeta',d/'raw.rmeta');dr=run(st,state+'-header',['-Zls=root','libproducer.rmeta'])
        h=(dr/'stdout').read_text().splitlines();group[state]=dict(size=(d/'raw.rmeta').stat().st_size,raw=sha(d/'raw.rmeta'),private=h[2],public=h[3],macro_stderr=(d/'stderr').read_text().splitlines()[-3:])
    r[variety]=group;dump(out/'results.json',r);print(variety,[group[s]['size'] for s in ['warm','clean','clean-repeat']],[group[s]['raw'][:9] for s in ['warm','clean','clean-repeat']],flush=True)
dump(out/'complete.json',dict(driver=sha(image),results=sha(out/'results.json')))
