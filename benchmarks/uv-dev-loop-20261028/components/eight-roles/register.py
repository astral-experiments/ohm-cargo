import hashlib,os,random,subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
if (HERE/'plan.json').exists():raise SystemExit('registration already exists')
assert not SLOTS.exists() and not os.path.lexists(TARGET)
orig=subprocess.check_output(['git','-C',str(W/'uv'),'show',f'{REVISION}:{EDIT_PATH}'])
assert orig==EDIT.read_bytes()
frozen={}
for n,letter,seed,start,cells in [('initial','k',440813359,10,['native/base','count/candidate','native/candidate','count/base']),('replica','q',440813843,40,['native/candidate','count/base','native/base','count/candidate'])]:
    order=['AB','BA']*4;random.Random(seed).shuffle(order)
    ids=list(range(start,start+8));random.Random(seed^0x8E71F).shuffle(ids)
    frozen[n]={'letter':letter,'seed':seed,'orders':order,'edits':ids,'admission_order':cells,'edits_sha256':{str(i):hashlib.sha256(edit_bytes(orig,letter,i)).hexdigest() for i in [0,1]+ids},'source_bytes':len(edit_bytes(orig,letter,start))}
receipt={'source_uv':REVISION,'edit_path':str(EDIT_PATH),'command':CMD,'cpus':list(range(24,32)),'source':str(SRC),'target':str(TARGET),'private_slots':str(SLOTS),'seed':str(SEED),'cargo_home':str(HOME_DIR),'pristine':input_state(),'workspace_lock_sha256':digest(SRC/'Cargo.lock'),'workspace_manifest_sha256':digest(SRC/'Cargo.toml'),'arm_hashes':{arm:{'cargo':digest(a),'wild':digest(b)} for arm,(a,b) in ARMS.items()},'rustc_sha256':digest(RUST/'rustc'),'rustdoc_sha256':digest(RUST/'rustdoc'),'wrapper_sha256':digest(WRAP),'counter_sha256':digest(COUNTER),'previous_calibration_sha256':digest(W/'tree-count/calibration/PASS.json'),'pgo_training_audit_sha256':digest(W/'pgo-confirmation-v2/audit.json'),'cohorts':frozen,'qualification':(HERE/'registration.md').read_text(),'code_sha256':{n:digest(HERE/n) for n in ['common.py','run.py','summarize.py','register.py','registration.md']}}
assert receipt['pristine']['target_absent'] and tuple(receipt['arm_hashes']['base'].values())==('51b59d549a21422809d865449be5a4c5b422989b22f7a314c6f18e7ab92b0855','82a927b86f929b67c58be4d37ab8442f32fcdd115d97334dcc5ac190101d8865')
assert tuple(receipt['arm_hashes']['candidate'].values())==('4a61560c17f00e54595122846f5450e7eb6a5ed3da9611ae39f4ecb972ab30d4','901b68fc9ca30975d837d45dcf1bdf743a6130ecef5e23d6aef44558b09bd7e1')
assert receipt['rustc_sha256']=='7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c'
save(HERE/'plan.json',receipt);(HERE/'registered.sha256').write_text(digest(HERE/'plan.json')+'  plan.json\n')
print('Frozen',digest(HERE/'plan.json'),frozen['initial']['orders'],frozen['replica']['orders'])
