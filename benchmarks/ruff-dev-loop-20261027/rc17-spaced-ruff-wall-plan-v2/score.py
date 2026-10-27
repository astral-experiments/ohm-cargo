"""Measure ordinary unchanged Cargo commands only after both exact RC source arms pass."""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import traceback

import elf
from statistics_local import analyze

here = Path(__file__).resolve().parent
p = Path('/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027')
source = Path('/home/dev-user/code/oss/ruff-spaced-inputs-20261027')
logical = p / 'logical'
out = p / 'rc17-spaced-wall-v2'

def read(path):
    return json.loads(path.read_bytes())

def put(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def messages(path):
    stream = [json.loads(line) for line in path.read_bytes().splitlines()]
    assert stream[-1] == {'reason':'build-finished','success':True}
    units = [r for r in stream if r['reason']=='compiler-artifact']
    stable = [{k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')} for r in units]
    order = lambda v: sorted(json.dumps(row,sort_keys=True,separators=(',',':')) for row in v)
    return order(stable), order(r for r in stream if r['reason']=='compiler-message'), [r['target']['name'] for r in units if not r['fresh']]

def compare(name, a, b):
    if a == b:
        return None
    left, right = map(elf.normalize, name)
    assert left['normalized']==right['normalized'] and left['bytes']==right['bytes'], name
    assert left['rodata_entsize']==right['rodata_entsize'] or min(left['rodata_entsize'],right['rodata_entsize'])==0, name
    return [left,right]

class Arm:
    def __init__(self, workflow, role, bound):
        self.workflow, self.role = workflow, role
        self.name = bound['name']
        self.origin = p / ('matched-native-'+self.name)
        self.t = self.origin / workflow
        self.tn = logical / ('ruff target' if workflow=='package' else 'ruff-target')
        self.sdk = logical / ('Ohm-SDK' if workflow=='package' else 'Ohm SDK')
        self.state = out / 'copies' / (workflow+'-'+role)
        self.cmd = ['cargo','+ohm','test','--no-run',*(['-p','ty_project'] if workflow=='package' else ['--workspace']),'--locked','--offline','-j4']
        assert sha(self.origin/'complete.json')==bound['qualification']
        self.report = read(self.t/'call-3/product.json')
        self.products = self.report['native']
        assert len(self.products) == (4 if workflow=='package' else 110)
        history=read(self.t/'progress.json')
        for i in (2,3):
            row=history[i]
            if role=='C':
                assert not row['dirty'] and not row['rustc'] and row['wild']==0
            elif workflow=='package':
                assert row['rustc']=={'full':2,'link-only':1} and row['wild']==1
            else:
                assert row['rustc']=={'full':1,'link-only':50} and row['wild']==50
        self.roster,self.diagnostics,self.dirty = messages(self.t/'call-3/stdout')
        assert len(self.roster) == self.report['units'] == (303 if workflow=='package' else 619)
        assert sorted(self.dirty) == sorted(self.report['dirty'])
        assert (p/('matching-source-protocol-'+self.name)/'exit').read_text()=='0'
        self.sdkdata=read(self.origin/'sdk.json')
        assert self.sdkdata['arm']==bound['binding']
        self.hashes=read(self.t/'sysroot.json')['hashes']
        assert set(self.hashes.values())=={bound['binding'][s] for s in ('driver','frontend','cargo_sha','wild')}
        self.exe = self.report['executables'][0] if workflow=='package' else next(
            r['executable'] for r in (json.loads(line) for line in (self.t/'call-3/stdout').read_bytes().splitlines())
            if r['reason']=='compiler-artifact' and r['executable'] and r['target']['name']=='e2e' and Path(r['manifest_path']).parent.name=='ty_server')
        self.env=dict(HOME=str(logical/'home'),USER='dev-user',PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',
                      CARGO_HOME=str(logical/'cargo'),CARGO_TARGET_DIR=str(self.tn),CARGO_BUILD_BUILD_DIR=str(logical/'shared'),
                      CARGO_BUILD_JOBS='4',CARGO_NET_OFFLINE='true',RUSTUP_HOME=str(self.t/'rustup'),RUSTUP_TOOLCHAIN='ohm',
                      RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',GIT_OPTIONAL_LOCKS='0',LC_ALL='C.UTF-8',LANG='C.UTF-8')

    def command(self, dest, argv):
        route=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
               '--ro-bind',self.sdkdata['view'],str(self.sdk),'--ro-bind',self.sdkdata['deps'],str(self.sdk/'lib/rustlib')]
        for n in ('target','shared','cargo','home'):
            route.extend(['--bind',str(self.state/n),str(self.tn if n=='target' else logical/n)])
        return subprocess.run([*route,'--bind',str(dest),str(dest),'--chdir',str(source),'--',*argv],
                              stdin=subprocess.DEVNULL,env=self.env,capture_output=True)

    def prepare(self):
        subprocess.run(['cp','-a','--reflink=auto','--',self.t/'state',self.state],check=True)
        for n,h in self.products.items():
            orig=self.t/'state/target'/n;new=self.state/'target'/n
            assert not new.samefile(orig) and sha(new)==sha(orig)==h
        d=out/'priming'/(self.workflow+'-'+self.role);d.mkdir(parents=True)
        check=self.command(d,['sha256sum',*self.hashes]);assert check.returncode==0
        assert {line.split('  ',1)[1]:line.split('  ',1)[0] for line in check.stdout.decode().splitlines()}==self.hashes
        root=self.command(d,['rustc','+ohm','--print=sysroot']);assert root.returncode==0 and root.stdout.decode().strip()==str(self.sdk)
        put(d/'binding.json',{'hashes':self.hashes,'sysroot':str(self.sdk)})
        self.check_json(d)

    def outputs(self):
        current={n:sha(self.state/'target'/n) for n in self.products}
        variation={}
        for n,h in current.items():
            if h!=self.products[n]:
                assert self.role=='B',n
                variation[n]=compare((self.t/'state/target'/n,self.state/'target'/n),self.products[n],h)
        return current,variation

    def check_json(self, where):
        check=self.command(where,[*self.cmd,'--message-format=json'])
        (where/'fresh.stdout').write_bytes(check.stdout);(where/'fresh.stderr').write_bytes(check.stderr)
        assert check.returncode==0 and b'Blocking waiting' not in check.stderr
        roster,diagnostics,dirty=messages(where/'fresh.stdout')
        assert roster==self.roster and diagnostics==self.diagnostics and sorted(dirty)==sorted(self.dirty)
        return dirty

    def slot(self,where):
        where.mkdir(parents=True)
        result=self.command(where,['/usr/bin/python3','-B',str(here/'clock.py'),str(where),*self.cmd])
        assert result.returncode==0 and not result.stdout and not result.stderr, (self.workflow,self.role,where)
        clock=read(where/'clock.json')
        assert clock['argv']==self.cmd and clock['returncode']==0 and clock['elapsed_ns']==clock['stop']-clock['start']>0
        stderr=(where/'stderr').read_bytes()
        assert not (where/'stdout').read_bytes() and b'Finished' in stderr and b'Blocking waiting' not in stderr
        current,variation=self.outputs()
        tests=self.command(where,[self.exe,'--list','--format','terse'])
        (where/'list.stdout').write_bytes(tests.stdout);(where/'list.stderr').write_bytes(tests.stderr)
        assert tests.returncode==0 and sha(where/'list.stdout')==self.report['oracle'] and sha(where/'list.stderr')==sha(self.t/'call-3/list.stderr')
        put(where/'verified.json',{'workflow':self.workflow,'role':self.role,'native':current,'variation':variation,
                                   'list':self.report['oracle'],'ns':clock['elapsed_ns']})
        return clock['elapsed_ns']

def clean(plan):
    git=lambda *args:subprocess.check_output(['git','--no-optional-locks','-C',source,*args])
    assert git('rev-parse','HEAD').decode().strip()==plan['source'] and not git('status','--porcelain','-z')
    assert hashlib.sha256(git('ls-files','-s','-z')).hexdigest()==plan['index']

def main():
    assert socket.gethostname()=='charlie-ohm-cargo5-build-1025' and not out.exists()
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True)
    plan=read(here/'plan.json');grant=read(here/'grant.json')
    assert grant['manifest']==sha(here/'SHA256SUMS') and all(len(grant[k])==40 for k in ('plan_commit','qualification_commit'))
    os.sched_setaffinity(0,set(plan['affinity']));assert sorted(os.sched_getaffinity(0))==plan['affinity']
    assert (p/'sdk-workspace-stock-registration-v2/exit').read_text()=='0' and shutil.disk_usage(p).free>65*2**30
    assert grant['profile_gate'] is True and grant['sources']==plan['sources']
    assert len(grant['safety_commit'])==40 and grant['safety_gate'] is True
    with (p/'matched-qualify.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        clean(plan);out.mkdir(mode=0o700);(out/'copies').mkdir()
        put(out/'elf-selftest.json',elf.selftest());rows={};cross={};all_arms={}
        for workflow in ('package','workspace'):
            arms={a:Arm(workflow,a,grant['arms'][a]) for a in 'BC'}
            all_arms[workflow]=arms
            b,c=arms.values()
            assert b.roster==c.roster and b.diagnostics==c.diagnostics and b.report['oracle']==c.report['oracle']
            assert b.products.keys()==c.products.keys() and b.report['executables']==c.report['executables']
            cross[workflow]={}
            for n,h in b.products.items():
                if h!=c.products[n]:
                    cross[workflow][n]=compare((b.t/'state/target'/n,c.t/'state/target'/n),h,c.products[n])
            for arm in arms.values():arm.prepare()
            put(out/'cross-arm.json',cross)
        for workflow,arms in all_arms.items():
            rows[workflow]=[]
            for i,order in enumerate(plan['orders'][workflow],1):
                ns={a:arms[a].slot(out/workflow/f'{i:02}-{a}') for a in order}
                rows[workflow].append({'order':order,'ns':ns});put(out/('ledger-'+workflow+'.json'),rows[workflow])
            for a,arm in arms.items():
                dest=out/'final'/(workflow+'-'+a);dest.mkdir(parents=True)
                arm.check_json(dest);arm.outputs()
                assert all(sha(arm.t/'state/target'/n)==h for n,h in arm.products.items())
        clean(plan);put(out/'all.json',rows);put(out/'result.json',analyze(plan,rows))
        put(out/'complete.json',{'manifest':sha(here/'SHA256SUMS'),'grant':sha(here/'grant.json'),'commands':2*sum(map(len,rows.values()))})

if __name__=='__main__':
    try:
        main()
    except BaseException:
        if out.is_dir():(out/'failure.txt').write_text(traceback.format_exc())
        raise
