"""Cross-check each designated Ron output against prior real consuming rustc commands and all four anchors."""
import ast,fcntl,hashlib,json,re
from pathlib import Path
h=Path.home()/'.cache/ohm-233-position-qualified-20261027';pr=h/'prefetch-fifo-qualified-v2';v1=h/'whole-ruff-observer-prefetch-fifo-v1';v2=h/'whole-ruff-observer-prefetch-fifo-v2'
take=lambda p:json.loads(p.read_bytes())
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-measure.lock').open('a') as f:
 fcntl.flock(f,fcntl.LOCK_EX)
 assert (pr/'anchors.rc').read_text().strip()=='0' and not list(v2.glob('timed-*'))
 start=take(pr/'rejected-v1-and-starting-state.json');cert=take(v2/'anchors-complete.json');active,=[n for n in start['proofs'] if n['role']=='active'];passive,=[n for n in start['proofs'] if n['role']=='passive']
 output={'anchors_sha256':digest(v2/'anchors-complete.json'),'certificate':cert,'anchor_status':{},'consumers':[]}
 for mode in ('build','test'):
    for arm in 'VC':
        place=v2/f'anchor-{mode}-{arm}';raw=take(place/'anchor.json');record=take(place/'receipt.json')
        assert digest(place/'anchor.json')==cert['anchors'][mode][arm] and not record['dirty'] and not record['processes']['rustc']
        assert len(raw['all_observers'])==len(raw['passive_observers'])==(mode=='test')
        if mode=='test':
            md,=[n for n in raw['active_artifact']['filenames'] if n.endswith('.rmeta')];assert md==active['metadata'] and raw['proofs'][0]['sha256']==active['encoded_sha256'] and raw['passive_proofs'][0]['sha256']==passive['encoded_sha256']
        output['anchor_status'][mode+arm]={'units':record['units'],'ELFs':len(raw['elf']),'execs':len(raw['executables']),'roster':raw['roster_sha256'],'active_proofs':raw['proofs'],'passive_proofs':raw['passive_proofs'],'reader_metadata':raw['reader_metadata'],'scanned_depinfo':raw['scanned_compiler_dep_info'],'registry_proof_files':raw['cache_inventory']['.ohm-registry-json-v1']['files']}
 for phase in ('prepare-test-V','prepare-test-C'):
    d=v1/phase;r=take(d/'receipt.json')
    for n,exe in r['processes']['executions']:
      if not exe.endswith('/rustc'):continue
      where=d/n
      for line in where.read_text().splitlines():
        if '"--extern", "ron=' not in line or not line.rstrip().endswith('= 0'):continue
        m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m
        av=[ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])]
        paths=[v.split('=',1)[1] for i,v in enumerate(av) if i and av[i-1]=='--extern' and v.startswith('ron=')]
        for v in paths:assert Path(v).parent==Path(active['metadata']).parent and Path(v).stem==Path(active['metadata']).stem
        assert paths;output['consumers'].append({'phase':phase,'process':n,'crate':av[av.index('--crate-name')+1],'extern_ron':paths,'source_trace_sha256':digest(where)})
 assert output['consumers'];print(json.dumps(output,sort_keys=True,indent=2))
