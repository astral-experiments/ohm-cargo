#!/usr/bin/env python3
"""Exercise a retained physical Ruff CLI with the seven same native behavior checks."""
import argparse
import tempfile
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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path)
    parser.add_argument('--compiler',choices=['P','Q'],required=True)
    parser.add_argument('--branch',choices=['A','B'],required=True)
    parser.add_argument('--admission',type=Path,default=Path(__file__).resolve().with_name('native-admission.json'))
    args=parser.parse_args();proof=json.loads(args.admission.read_bytes())
    exe=args.binary.resolve(strict=True)
    with exe.open('rb') as f:observed=hashlib.file_digest(f,'sha256').hexdigest()
    expected=proof['cross_role'][args.branch]['complete_ELF_sha256']['PQ'.index(args.compiler)]
    if observed!=expected:raise SystemExit('The supplied ELF differs from that enrolled branch and compiler.')
    with tempfile.TemporaryDirectory() as tmp:
        where=Path(tmp)
        result=cli_checks(where,exe,dict(os.environ,HOME=tmp),where,proof['source'][args.branch])
    print(json.dumps({'sha256':observed,'branch':args.branch,'compiler':args.compiler,'statuses':{k:v['status'] for k,v in result.items()}},sort_keys=True))
if __name__=='__main__':main()
