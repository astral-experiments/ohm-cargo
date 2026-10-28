"""Replay the unchanged H5 packet, then challenge the overlay using in-memory evidence."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_compat as compat

ROOT=HERE.parent
PACKET=ROOT/'rc17-composed-early-wall-results-v3c'
ARGS=[PACKET/'terminal.json.gz', ROOT/'rc17-composed-early-wall-plan-v3c', ROOT/'rc17-composed-early-native-results',
      PACKET/'published-pins.json',ROOT/'rc17-composed-all-links-results','--admission-results',
      ROOT/'rc17-composed-wall-admission-v3c','--h2-results',ROOT/'rc17-text-size-first-selection-wall-results']
PACKET_SHA='209a7f6c618dc34e3dd1aa26dfd65fc3cb01b91c61751269c92f165ef029b34f'
PINS_SHA='64413650cee5ac05f0d95577e92cfd4931ca666b49a3eb6ae71bd3a0c8b6f57c'
WORKER_SHA='9c2e4138072679b8ffff20d417fffad8f6bcd3cba1b0dd15309e2d935cbc0813'
SCORER_SHA='cdea262f581fee6047b8e02e598513bed78cc58ecbab8eeb33208db8b05dc57f'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def obj(p):
    return json.loads(p.read_bytes())

def compare_help():
    def args(path):
        r=subprocess.run([sys.executable,'-IB',path,'--help'],check=True,capture_output=True,text=True)
        return r.stdout.strip().split('positional arguments:')[1]
    assert args(HERE/'verify_compat.py')==args(compat.RECEIVER/'verify.py')

def bodies(packet):
    return lambda path:packet['bodies'][packet['files'][path]['sha256']]

def changed_body(packet,path,text):
    """Recompute the mutated receipt correctly so a mere body SHA mismatch cannot explain rejection."""
    next_packet=dict(packet)
    files=next_packet['files']=dict(packet['files'])
    data=next_packet['bodies']=dict(packet['bodies'])
    old=files[path];assert old['capture']=='verbatim'
    new=text.encode();digest=sha(new);data[digest]=text
    files[path]={**old,'sha256':digest,'bytes':len(new)}
    if all(f['sha256']!=old['sha256'] for f in files.values() if f['capture']=='verbatim'):
        del data[old['sha256']]
    return next_packet

def reject(call,line):
    try:call()
    except AssertionError as err:
        checked=[f for f in traceback.extract_tb(err.__traceback__) if Path(f.filename).name=='verify.py' and f.name=='check_packet']
        assert any(f.lineno==line for f in checked),(line,[(f.lineno,f.name) for f in checked])
        return line
    raise AssertionError('altered record was accepted')

def main():
    compare_help()
    pbytes=ARGS[0].read_bytes();assert sha(pbytes)==PACKET_SHA and sha(ARGS[3].read_bytes())==PINS_SHA
    worker=ROOT/'rc17-composed-early-native-workspace-plan/ruff_worker.py';assert sha(worker.read_bytes())==WORKER_SHA
    assert sha((ARGS[1]/'runner.py').read_bytes())==SCORER_SHA and obj(ARGS[1]/'plan.json')['native_worker']==WORKER_SHA
    # Reproduce the failure using the unmodified published verifier executable and its original CLI.
    original=subprocess.run([sys.executable,'-IB',compat.RECEIVER/'verify.py',*ARGS],capture_output=True,text=True)
    assert original.returncode==1 and not original.stdout and 'line 121, in check_packet' in original.stderr and compat.OLD in original.stderr
    # Run the successful overlay through the same CLI, including the external immutable native/admission/H2 records.
    actual=subprocess.run([sys.executable,'-IB',HERE/'verify_compat.py',*ARGS],check=True,capture_output=True)
    assert actual.stderr==b''
    result=json.loads(actual.stdout);assert result['terminal']=='complete' and result['verified_slots']==result['observed_clocks']==48 and result['complete_pair_checkpoints']==24
    v=compat.load('_mutation_test');p=json.loads(gzip.decompress(pbytes));raw=bodies(p);plan=obj(ARGS[1]/'plan.json');schedule=[(i,j,arm,f'{i:02d}-{j}-{arm}') for i,arms in enumerate(plan['order'],1) for j,arm in enumerate(arms,1)]
    prior=v['original_native'](ARGS[2]);public=v['bind_external'](obj(ARGS[3]),ARGS[4],ARGS[6],ARGS[8])
    def check(q):return v['check_packet'](q,ARGS[1],prior,public)
    score='launcher/score.out';text=raw(score);lines=text.splitlines(keepends=True)
    want=compat.expected_score_stdout(schedule,lambda path:json.loads(raw(path)),p['slots'])
    assert text==want and len(lines)==72
    assert result['statistics']==json.loads(raw('result/result.json'))==json.loads(raw('launcher/verify.out'))['statistics']
    edits={
        '24_pair_lines_without_the_worker_output':''.join(lines[2::3]),
        'missing_second_audit':''.join(lines[:1]+lines[2:]),
        'extra_audit':lines[0]+text,
        'pair_boundary_before_audit':''.join([lines[0],lines[2],lines[1],*lines[3:]]),
        'incorrect_pair_ordinal':text.replace('1/24 guarded pairs','2/24 guarded pairs',1),
        'altered_typed_fresh_count':text.replace('fresh 563','fresh 562',1),
        'altered_ELF_count':text.replace('ELF 110','ELF 109',1),
        'altered_job_count':text.replace("'link-only': 50","'link-only': 49",1),
        'wrong_physical_process_order':text.replace("'full': 1, 'link-only': 50","'link-only': 50, 'full': 1",1),
        'missing_terminal_newline':text.rstrip('\n'),
    }
    for changed in edits.values():assert changed!=text
    rejected={}
    for k,changed in edits.items():
        q=changed_body(p,score,changed);rejected[k]=reject(lambda:check(q),121)
    # The same changed text and product would agree with each other. The independent physical jobs still rule it out.
    path='01-1-B/unchanged/products.json';products=json.loads(raw(path));products['counts']['link-only']-=1
    q=changed_body(changed_body(p,score,edits['altered_job_count']),path,json.dumps(products))
    rejected['simultaneously_altered_product_and_console_counts']=reject(lambda:check(q),121)
    # Confirm a later validity gate continues to reject a coherent, rehashed observation with the original stdout.
    path='01-1-B/verified.json';verified=json.loads(raw(path));verified['elapsed_ns']+=1
    q=changed_body(p,path,json.dumps(verified))
    rejected['slot_duration_mismatches_raw_clock']=reject(lambda:check(q),152)
    assert sha(ARGS[0].read_bytes())==PACKET_SHA and sha(ARGS[3].read_bytes())==PINS_SHA
    print(json.dumps(dict(packet_sha256=PACKET_SHA,pinned_reader_sha256=compat.SOURCE_SHA256,original_exit=original.returncode,
        original_rejection={'file':'verify.py','function':'check_packet','line':121},overlay_exit=actual.returncode,
        terminal=result['terminal'],verified_slots=result['verified_slots'],verified_pairs=result['complete_pair_checkpoints'],raw_score_stdout_bytes=len(text.encode()),
        raw_score_stdout_sha256=sha(text.encode()),unchanged_audit_lines=48,pair_completion_lines=24,progress_mutations=sorted(edits),full_verifier_rejections=rejected,
        physical_verifier_statistics_identical=True,projected_native_jobs=sum(len(s['jobs']) for s in p['slots'].values()),
        subsequent_unmodified_verifier_failures=0),sort_keys=True,indent=2))

if __name__=='__main__':main()
