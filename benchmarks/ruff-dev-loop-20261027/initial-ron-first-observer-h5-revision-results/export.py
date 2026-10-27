"""Export verified completed wall-study slots after the entire registered run reaches its terminal state."""
from pathlib import Path
import csv,gzip,hashlib,json,sys
target=sys.argv[1]
if target=='h4':p=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');r=p/'ron-first-shipping-worker-field-v2-20261027';bound=r/'bound-v2-45d9876d';want=54
elif target=='h5':p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');r=p/'ron-first-replication-ffield-v2';bound=r/'bound-replica-a63f1f78';want=24
else:raise ValueError('unknown fixed host')
j=lambda f:json.loads(f.read_bytes())
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
assert (r/'score.rc').is_file() and (r/'score.rc').read_text().strip()=='0';series=r/'native-scores';outer=j(series/'complete.json');tables=(series/'times.csv').read_bytes();rows=list(csv.DictReader(tables.decode().splitlines()));assert len(rows)==outer['slots']==want
assert sha(bound/'SHA256SUMS')==outer['runner'] and sha(bound/'plan.json')==outer['plan']
assert sha(series/'times.csv')==outer.get('times_sha256',outer.get('observations'))
sys.path.insert(0,str(bound));from elf_gate import permitted_linker_width
samples={};roster_ref=None;native_refs={};input_sets={}
# Each completed training record was checked against its actual on-disk bytes before its state was retired.
physical_rows=j(r/'results/qualify-C/proof-validation.json')['cold']['physical_inputs']
names={name for path,*rest in physical_rows for name in Path(path).parts if hashlib.sha256(name.encode()).hexdigest()=='85e1e016efd01b791bbc91cd0960c7f9de002a7f374d60c2a299adf9ebfa1381'}
registry_dir,=names;private_prefix=registry_dir.rsplit('-',1)[0];assert private_prefix and private_prefix!=registry_dir
for row in rows:
    arm=row['arm'];name=f"score-{int(row['block']):02d}-{int(row['slot'])}-{arm}";d=r/'results'/name;b=j(d/'complete.json');proof=j(d/'proof-validation.json');other=j(d/'same-subject-reference.json');assert b['mode']=='native'
    cmd={}
    for ph in ('cold','first','settled'):
        sub=d/ph;v=b['phases'][ph];assert v['elapsed_ns']==int(row[ph+'_ns'])==j(sub/'status.json')['elapsed_ns'] and (sub/'status.json').is_file()
        assert v['native']==sha(sub/'native.json') and v['cargo_stdout']==sha(sub/'stdout') and v['cargo_stderr']==sha(sub/'stderr')
        n=j(sub/'native.json');ref=j(r/'results'/('qualify-'+arm)/ph/'native.json');assert len(n)==len(ref)==110 and n.keys()==ref.keys()
        native_refs[arm+'/'+ph]=ref
        delta=[k for k in n if n[k]!=ref[k]];assert sorted(delta)==sorted(other[ph]) and all(permitted_linker_width(n[k],ref[k]) for k in delta)
        raw=proof[ph];assert raw['depinfo_sha256']==v['ron_depinfo'] and raw['encoded_sha256']==v['ron_fingerprint']
        assert v['checksums']==len(raw['physical_inputs'])==(45 if arm=='C' or ph!='cold' else 0)
        assert v['fresh']=={'cold':0,'first':619 if arm=='C' else 563,'settled':619}[ph]
        artifacts=[a for line in (sub/'stdout').read_bytes().splitlines() if (a:=json.loads(line)).get('reason')=='compiler-artifact'];assert len(artifacts)==619
        exe=[x for x in artifacts if x['executable']];assert len(exe)==102 and sum(x['profile']['test'] for x in exe)==84
        if roster_ref is None:roster_ref=v['roster']
        assert v['roster']==roster_ref
        physical=[[a.replace(private_prefix,'$REGISTRY'),*z] for a,*z in raw['physical_inputs']]
        proof_id=hashlib.sha256(json.dumps(physical,sort_keys=True,separators=(',',':')).encode()).hexdigest();input_sets[proof_id]=physical
        cmd[ph]=dict(checked_physical_input_set=proof_id,cmd={k:v[k] for k in ('fresh','cargo_stdout','cargo_stderr','roster','native','ron_complete','ron_fingerprint','ron_depinfo','ron_rlib','ron_rmeta','checksums','elapsed_ns')},native=n,proof_record_hash={k:raw[k] for k in ('depinfo_sha256','encoded_sha256','seal_blake3')},same_subject_diff=delta,executables=102,test_harnesses=84,ordinary_binaries_and_examples=18)
    assert cmd['first']['native']==cmd['settled']['native'] and (arm!='C' or cmd['cold']['native']==cmd['first']['native'])
    samples[name]=dict(command=cmd,ordinary=b['ordinary_native_oracles'],host_sha=sha(d/'host.json'),full_receipt_sha=sha(d/'complete.json'),proof_file_sha=sha(d/'proof-validation.json'))
x={'host':target,'series':outer,'manifest':sha(bound/'SHA256SUMS'),'raw_csv_file_sha256':sha(series/'times.csv'),'times_csv':tables.decode(),'samples':samples,'same_subject_natives':native_refs,'validated_input_sets':input_sets}
raw=json.dumps(x,sort_keys=True,separators=(',',':')).encode();assert all(t not in raw for t in (b'/home/dev-user/',b'/mnt/devbox',private_prefix.encode(),b'Authorization'))
sys.stdout.buffer.write(gzip.compress(raw,compresslevel=9,mtime=0))
