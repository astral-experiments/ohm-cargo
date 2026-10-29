import collections,hashlib,json,os
from pathlib import Path
Y=Path(__file__).resolve().parent
D=Y/'archive-fs-restore/incumbent';x=json.loads((D/'result-v2.json').read_bytes())
P=Path.home()/'.cache/ohm-ty-vendored-script-consumer-20261028-v1'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
scoped=[]
for label in ['warm','cold']:
    target=P/label/'target/debug'
    assert target.is_dir()
    named=sorted(target.glob('*.rlib'));old=target/'libruff_python_parser.rlib';assert not old.exists()
    scoped.append({'state':label,'root_archive_files':[{'name':v.name,'sha256':sha(v),'bytes':v.stat().st_size}for v in named],
                   'top_level_parser_rlib':os.path.lexists(old)})
    assert [v.name for v in named]==['libty_vendored.rlib']
print(scoped)
rows=[]
for v in x['rows']:
    top=Y/'active/target/debug'/v['prior_reported_rlib'][0]
    rust_argv=next(line for line in (Y/'archive-fs-restore/raw'/('exec.'+str(v['rustc_root']))).read_text().splitlines()if line.startswith('execve(')and '"--crate-name"'in line and line.endswith('= 0'))
    import ast,re
    av=ast.literal_eval(re.match(r'^execve\("[^"\\]*", (\[.*\]), ',rust_argv)[1]);out=Path(av[av.index('--out-dir')+1]);unit=out/v['unit_rlib'];assert os.path.samefile(top,unit)
    inc=Path(next(a.split('=',1)[1] for a in av if a.startswith('incremental=')))
    sub=list(inc.glob(v['crate']+'-*'));assert sub
    inc_archive_paths=[str(b.relative_to(q))for q in sub for b in q.rglob('*.rlib')];assert not inc_archive_paths
    rows.append({'crate':v['crate'],'unit_uplift_same_after':True,'size_after':top.stat().st_size,'published_sha256':sha(top),'links_after':top.stat().st_nlink,'incremental_rlib_count_after':0})
(D/'aftermath.json').write_text(json.dumps({'whole_workspace':rows,'separate_package_selected':scoped},sort_keys=True,indent=2)+'\n')
