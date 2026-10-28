"""Read-only complete startup, single-level tool bindings, and genuine old/new trace visibility."""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path


def guarded_start(ctx):
    original=Path.mkdir;expected=ctx['R']/'captures/seed-repeat2';seen=[]
    class Ready(Exception):pass
    def check(p,*a,**k):
        assert p==expected,(p,expected);seen.append(str(p));raise Ready()
    Path.mkdir=check
    try:
        try:ctx['run']()
        except Ready:pass
        else:raise AssertionError('unexpected completion')
    finally:Path.mkdir=original
    assert seen==[str(expected)] and not expected.exists()


def test(flat,bootstrap_src):
    ns=flat.namespaces(read_only=True)
    here=Path(__file__) if '__file__' in globals() else None
    assert here is not None
    command='''import types
b=types.ModuleType("b");exec(%r,b.__dict__);p=types.ModuleType("p");exec(%r,p.__dict__);p.guarded_start(b.context())
print("startup qualified")'''%(bootstrap_src,here.read_text())
    q=subprocess.run([*ns,'/usr/bin/python3','-IB','-c',command],check=True,capture_output=True,text=True)
    assert 'qualified command seed-repeat1 48' in q.stdout and 'startup qualified' in q.stdout
    n=flat.load(flat.K/'ruff_worker.py');stock=n.sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    orig=flat.OLD;new=flat.NEW;current=flat.read(new/'tree-before-resume.json')
    checks={}
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for phase,role,edited in [('seed-repeat2','observer',False),('selected-observer','observer',True),('selected-composed','composed',True)]:
            receipt=root/phase;receipt.mkdir();state=new/'states/seed'
            args,env,_=flat.namespace(n.invocation,state,role,edited,receipt,phase)
            # Keep the real application binds and this command’s temporary telemetry sink;
            # the probe itself writes only to its isolated receipt, then checks its bytes.
            endpoints=[str(n.src/n.scope),str(n.sdk/'bin/cargo'),str(stock),str(orig/'source/wild.py'),str(orig),str(new),str(receipt/'private-sentinel')]
            code='''import hashlib,json,os,sys;from pathlib import Path
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
a,b,c,d,old,new,out=sys.argv[1:];assert Path(old).samefile(new);Path(out).write_bytes(b"registered namespace probe\\n")
print(json.dumps({"hashes":[h(f) for f in (a,b,c,d,out)],"phase":os.environ["WILD_PHASE"],"ino":Path(old).stat().st_ino}))'''
            r=subprocess.run([*args,'/usr/bin/python3','-IB','-c',code,*endpoints],env=env,capture_output=True,text=True,check=True)
            data=json.loads(r.stdout);assert data['ino']==current['host_visible_copy_inode']!=orig.stat().st_ino
            expected=[n.hash1 if edited else n.hash0,n.sealed_file(role)[1],flat.sha(new/'wild-wrapper'),flat.sha(new/'source/wild.py'),
                      hashlib.sha256(b'registered namespace probe\n').hexdigest()]
            assert data['phase']==phase and data['hashes']==expected and (receipt/'private-sentinel').read_bytes()==b'registered namespace probe\n'
            checks[phase]=data
    # Under the final verifier's single read-only namespace, reread an actual prior
    # default stock child's literal exec and a field-checked retained ELF.
    code='''import sys,json;from pathlib import Path
root=Path(%r);sys.path.insert(0,str(root/'source'));from verify import process,body_info
cube=next((root/'captures/failure-1').iterdir());c=json.loads((cube/'capture.json').read_bytes());argv=json.loads((cube/'raw-argv.json').read_bytes())
print(json.dumps({"stock_trace":process(root/'commands/failure-1/trace',c["default_pid"],argv),"raw_elf":body_info(root/'bodies'/c["raw_sha256"])["sha256"]}))'''%str(orig)
    final=json.loads(subprocess.run([*ns,'/usr/bin/python3','-IB','-c',code],capture_output=True,text=True,check=True).stdout)
    assert final['raw_elf']=='f56d2f9441e7bae586e8ed95bcbaf58b6753337347afb26da1f2a05a305a4701'
    return {'complete_frozen_startup_before_first_new_write':True,'true_prior_seed_native_row_count':48,'new_native_processes':0,
            'single_namespace_sdk_and_source_bindings':checks,'old_root_unchanged_inode':orig.stat().st_ino,
            'source_wild_unchanged':flat.sha(orig/'source/wild.py'),'source_native_check_unchanged':flat.sha(orig/'source/verify.py'),
            'original_real_trace_rechecked_in_final_mode':final,'nested_bwrap':'disabled on this host; no nested launch used'}
