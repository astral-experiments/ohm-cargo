from pathlib import Path
import collections,hashlib,json,os,subprocess
def sha(b):return hashlib.sha256(b).hexdigest()
def cli_checks(d,bin,env,cwd,rev):
    import re
    def go(tag,args,data=b'',code=0):
        p=subprocess.run([bin,*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=cwd,timeout=50)
        for f,x in [('stdout',p.stdout),('stderr',p.stderr)]:
            with (d/(tag+'.'+f)).open('xb') as h:h.write(x)
        row={'argv':args,'status':p.returncode,'stdin_sha256':sha(data),'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)}
        assert p.returncode==code,(tag,row,p.stdout[-1200:],p.stderr[-1200:])
        return p,row
    normal=['check','--isolated','--no-cache','--select','E711','--stdin-filename','branch_probe.py']
    current=b'def enabled(value):\n    if value is None:\n        return 1\n    return 0\n'
    lint=current.replace(b'value is None',b'value == None')
    malformed=b'def enabled(value)\n    return True\n'
    verdict={}
    p,verdict['version']=go('ruff-version',['--version']);assert b'0.16.7' in p.stdout
    p,verdict['source']=go('ruff-version-json',['version','--output-format','json'])
    vv=json.loads(p.stdout);assert vv['version']=='0.16.7' and vv['commit_info']['commit_hash']==rev and vv['commit_info']['short_commit_hash']==rev[:9],vv
    p,verdict['clean']=go('ruff-clean',[*normal,'--output-format','json','-'],current);assert json.loads(p.stdout)==[]
    p,verdict['warning']=go('ruff-warning',[*normal,'--output-format','json','-'],lint,1)
    w=json.loads(p.stdout);assert len(w)==1 and w[0]['code']=='E711' and w[0]['location']['row']==2 and w[0]['fix']
    p,verdict['fixed']=go('ruff-fix',[*normal,'--fix','--unsafe-fixes','--exit-non-zero-on-fix','-'],lint,1)
    assert p.stdout==current,p.stdout
    p,verdict['recheck']=go('ruff-recheck',[*normal,'--output-format','json','-'],p.stdout);assert json.loads(p.stdout)==[]
    p,verdict['invalid']=go('ruff-invalid',[*normal,'--output-format','json','-'],malformed,1)
    err=json.loads(p.stdout);assert any(str(v.get('code')).lower()=='invalid-syntax' or 'syntax' in str(v.get('message')).lower() for v in err),err
    return verdict
def kernel_execs(d,k):
    import ast,re
    exe_sdk=(k/'bin/rustc').resolve()
    wild=(k/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd').resolve()
    rows=[]
    for p in sorted((d/'trace').glob('event.*')):
        for ln in p.read_bytes().splitlines():
            if not ln.startswith(b'execve(') or not ln.rstrip().endswith(b' = 0'):continue
            m=re.match(rb'^execve\(("(?:\\.|[^"\\])*"), (\[.*?\]), ',ln)
            assert m,(p,ln[:160]);exe=Path(ast.literal_eval(m[1].decode()));args=ast.literal_eval(m[2].decode());role=None
            physical=exe.resolve()
            if physical==exe_sdk and '--crate-name' in args and '--out-dir' in args:role='SDK rustc'
            elif physical==wild:role='stock Wild'
            elif exe.name=='collect2':role='collect2'
            elif physical.name.endswith(('-gcc','gcc','gcc-13')) or exe.name in ('gcc','cc'):role='GCC'
            elif exe.name.startswith('build-script-') or exe.name.startswith('build_script_'):role='build script'
            if role:
                crate=args[args.index('--crate-name')+1] if '--crate-name' in args else None
                rows.append({'role':role,'crate':crate,'pid':int(p.name.split('.')[-1]),'executable':str(physical),'argv':args})
    by=collections.Counter(v['role'] for v in rows)
    return rows,dict(by)
