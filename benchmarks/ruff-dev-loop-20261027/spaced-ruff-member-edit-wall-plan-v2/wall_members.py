"""Score the true typeshed edit and unchanged ordinary member builds after the native contract."""
from pathlib import Path
import fcntl,hashlib,importlib.util,json,os,shutil,socket,subprocess,sys,traceback,zipfile
here=Path(__file__).resolve().parent
p=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
source_k=p/'member-build-matched-protocol-v1';native=p/'member-build-matched-native-v1'
sys.path.insert(0,str(source_k));sys.path.insert(0,str(here))
spec=importlib.util.spec_from_file_location('qualified_ordinary_members',source_k/'matched_members.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from member_stats import analyze
from member_archive import witness
from member_reader import search_args,validate
from stub_bytes import read_stub
read=lambda f:json.loads(f.read_bytes())
plan=read(here/'plan.json')
contract=read(here/'contract.json')
out=p/'member-build-wall-v2'
q=m.q
put=q.put
cmd=['cargo','+ohm','build','--locked','--offline','-j4']
def typed(row):return sorted(json.dumps({k:x[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for x in row if x['reason']=='compiler-artifact')
def source_tag(package):return 'wasm' if package=='ty_wasm' else 'project'

class Arm:
    def __init__(self,image,package):
        self.image=image;self.pkg=package
        name=image+source_tag(package)
        src=native/(name+'-'+package);self.case=name+'-'+package;own=out/'states'/self.case;own.mkdir(parents=True)
        self.base=src;self.own=own;self.st=own/'state'
        subprocess.run(['cp','-a','--reflink=auto','--',src/'state',self.st],check=True)
        self.visible=own/'visible-functools.pyi';shutil.copy2(src/'visible-functools.pyi',self.visible)
        bind=read(src/'binding.json')
        self.reference=contract[self.case]
        assert set(bind['hashes'].values())=={m.plan['arms'][image]['driver'],m.plan['arms'][image]['cargo_sha'],m.plan['common']['frontend'],m.plan['common']['wild']}
        self.env=q.opts(self.st,q.sdk/'bin/cargo')[1]
        self.env.update(HOME=str(m.canonical/'home'),CARGO_TARGET_DIR=str(m.target),CARGO_BUILD_BUILD_DIR=str(m.canonical/'shared'),
                   CARGO_HOME=str(m.canonical/'cargo'),RUSTUP_HOME=str(native/('view-'+name)/'rustup'),CARGO_BUILD_JOBS='4')
        loc=read(source_k/'locations.json');driver=next(Path(n).name for n in bind['hashes'] if 'librustc_driver-' in n)
        self.br=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(m.images/loc['common']),str(m.sdk),
                 '--ro-bind',str(m.images/loc[image]['cargo']),str(m.sdk/'bin/cargo'),'--ro-bind',str(m.images/loc[image]['driver']),str(m.sdk/'lib'/driver)]
        for key in ('target','shared','cargo','home'):self.br+=['--bind',str(self.st/key),str(m.target if key=='target' else m.canonical/key)]
        self.search=search_args(src/'cold',package);self.source='original'
        assert q.sha(self.visible)==m.plan['stub']['original']
        self.roster=typed([json.loads(s) for s in (src/'cold/stdout').read_bytes().splitlines()])
        self.product_names=self.reference['original']['files'][0].keys()
        check=self.run(['sha256sum',*bind['hashes']],own);assert check.returncode==0
        assert {s.split('  ',1)[1]:s.split('  ',1)[0] for s in check.stdout.decode().splitlines()}==bind['hashes']
        first=next(iter(self.product_names));assert not (self.st/'target'/first).samefile(src/'state/target'/first)
    def run(self,argv,dot):
        return subprocess.run([*self.br,'--ro-bind',str(self.visible),str(q.src/m.stub),'--bind',str(dot),str(dot),
                               '--chdir',q.src/'crates'/self.pkg,'--',*argv],env=self.env,capture_output=True,stdin=subprocess.DEVNULL)
    def switch(self,stage):
        assert stage!=self.source
        data=(source_k/('stub-'+stage+'.pyi')).read_bytes();old=self.visible.stat().st_mtime_ns
        self.visible.write_bytes(data);assert self.visible.stat().st_mtime_ns>old and q.sha(self.visible)==m.plan['stub'][stage]
        self.source=stage
    def ordinary(self,dot):
        dot.mkdir(parents=True);ret=self.run([*cmd,'--message-format=json'],dot)
        (dot/'stdout').write_bytes(ret.stdout);(dot/'stderr').write_bytes(ret.stderr)
        assert ret.returncode==0 and b'Blocking waiting' not in ret.stderr
        rows=[json.loads(l) for l in ret.stdout.splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
        assert typed(rows)==self.roster and sorted(json.dumps(d,sort_keys=True) for d in rows if d['reason']=='compiler-message')==self.reference[self.source]['diagnostics']
        return sorted(x['target']['name'] for x in rows if x['reason']=='compiler-artifact' and not x['fresh'])
    def stats(self):
        return {n:[v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns,v.st_ctime_ns]
                for n in self.product_names for v in [(self.st/'target'/n).stat()]}
    def verify(self,dot):
        dot.mkdir(parents=True,exist_ok=True);r=self.reference[self.source];names=r['files'][0].keys()
        values={key:q.sha(self.st/'target'/key) for key in names}
        typed={};archives={}
        for n,raw in values.items():
            if n.endswith('.rlib'):
                desc=witness(self.st/'target'/n);assert desc['raw']==raw
                archives[n]=desc;typed[n]=desc['typed']
            else:typed[n]=raw
        assert typed==r['typed'],('new native product',self.case,self.source,[n for n in typed if typed[n]!=r['typed'][n]])
        if self.image=='C' and self.pkg=='ty_project':assert values==r['files'][-1]
        put(dot/'archives.json',archives)
        z=self.st/r['zip_path'];assert q.sha(z) in r['zips']
        exp=(source_k/('stub-'+self.source+'.pyi')).read_bytes()
        with zipfile.ZipFile(z) as archive:assert read_stub(archive,'stdlib/functools.pyi')==exp
        v=validate(self.pkg,dot,self.run,m.target,values,self.search,(source_k/'reader.rs').read_bytes(),exp)
        put(dot/'verified.json',dict(outputs=values,typed=typed,zip=q.sha(z),stage=self.source,caller=v))
    def clock(self,dot):
        dot.mkdir(parents=True);ret=self.run(['/usr/bin/python3','-B',str(here/'member_clock.py'),str(dot)],dot)
        assert ret.returncode==0 and not ret.stdout and not ret.stderr,(ret.returncode,ret.stderr[-500:])
        clock=read(dot/'clock.json');assert clock['argv']==cmd and clock['code']==0 and clock['ns']==clock['stop']-clock['start']>0
        assert not (dot/'stdout').read_bytes() and b'Finished' in (dot/'stderr').read_bytes() and b'Blocking waiting' not in (dot/'stderr').read_bytes()
        return clock['ns']

def main():
    assert socket.gethostname()=='charlie-ohm-pkg-build-1024' and (source_k/'exit').read_text()=='0' and (native/'complete.json').is_file()
    assert not out.exists() and not (p/'member-build-wall-v1').exists() and shutil.disk_usage(p).free>90*2**30
    grant=read(here/'grant.json');assert grant['native_sha']==q.sha(native/'complete.json') and grant['plan_sha']==q.sha(here/'SHA256SUMS')
    assert q.sha(here/'contract.json')==grant['contract_sha'] and all(len(grant[n])==40 for n in ('publication','native_publication','archive_publication','original_design'))
    assert grant['design_sha']=='083c5d3c93dce12563382f2c204e34b296ead53daf2fd25f3c8d24fefb0e05fa'
    os.sched_setaffinity(0,set(range(8)))
    with (p/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);q.source_gate();out.mkdir(mode=0o700)
        states={w:{image:Arm(image,w) for image in 'BC'} for w in ('ty_wasm','ty_project')}
        for w,arms in states.items():
            for image,arm in arms.items():
                base=out/'priming'/arm.case
                assert arm.ordinary(base/'original')==arm.reference['original']['settled_dirty']
                arm.verify(base/'original-check')
                if w=='ty_wasm':
                    for stage in ('reversed','original'):
                        arm.switch(stage)
                        got=arm.ordinary(base/(stage+'-edit'));assert got==arm.reference[stage]['edited_dirty']
                        arm.verify(base/(stage+'-dirty-check'))
                        assert arm.ordinary(base/(stage+'-repeat'))==arm.reference[stage]['settled_dirty']
                        arm.verify(base/(stage+'-settled-check'))
        ledger={k:[] for k in ('edit','first_unchanged','edit_plus_first','project_unchanged')}
        for i,order in enumerate(plan['orders']['wasm']):
            stage='reversed' if not i%2 else 'original';times={}
            for image in order:
                a=states['ty_wasm'][image];d=out/'wasm'/f'{i+1:02}-{image}';a.switch(stage)
                edit=a.clock(d/'edit');before=a.stats()
                repeat=a.clock(d/'repeat');after=a.stats()
                put(d/'first-repeat-stats.json',dict(before=before,after=after))
                if image=='C':assert before==after
                a.verify(d/'validation');times[image]=(edit,repeat)
            for name,fn in (('edit',lambda v:v[0]),('first_unchanged',lambda v:v[1]),('edit_plus_first',sum)):
                ledger[name].append(dict(order=order,direction=stage,b=fn(times['B']),c=fn(times['C'])))
            put(out/'wasm-progress.json',dict(count=i+1))
        for i,order in enumerate(plan['orders']['project']):
            times={}
            for image in order:
                a=states['ty_project'][image];d=out/'project'/f'{i+1:02}-{image}'
                times[image]=a.clock(d/'build');a.verify(d/'validation')
            ledger['project_unchanged'].append(dict(order=order,direction='original',b=times['B'],c=times['C']))
            put(out/'project-progress.json',dict(count=i+1))
        for w,arms in states.items():
            for image,a in arms.items():
                d=out/'final'/a.case;assert a.ordinary(d/'ordinary')==a.reference['original']['settled_dirty'];a.verify(d/'validation')
        q.source_gate();put(out/'ledger.json',ledger)
        put(out/'result.json',analyze(plan,ledger));put(out/'complete.json',dict(sessions=144,grant=q.sha(here/'grant.json')))
if __name__=='__main__':
    try:main()
    except BaseException:
        if out.is_dir():(out/'failure.txt').write_text(traceback.format_exc())
        raise
