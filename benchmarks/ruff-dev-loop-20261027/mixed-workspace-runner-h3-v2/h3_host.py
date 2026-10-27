"""Verify the selected hosts, inputs and receipts without starting Cargo or creating a target."""
import hashlib, json, os, shutil, socket, subprocess, sys
from pathlib import Path
from common import git, load, need, sha
from state import BASE, H, gate_free, source_clean

def check_h3(b):
    host=b['host']
    need(host['label']=='H3' and hashlib.sha256(socket.gethostname().encode()).hexdigest()==host['node_sha256'],'incorrect physical host')
    need(os.uname().release==host['kernel'] and os.cpu_count()==host['cpus'] and os.uname().machine==host['arch'],'host kernel/architecture/core count')
    model=next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name'))
    need(model==host['model'],'host CPU')
    mount_info=json.loads(subprocess.check_output(['findmnt','--target',str(BASE),'--json','--output','TARGET,SOURCE,FSTYPE,MAJ:MIN']))['filesystems']
    need(mount_info==host['physical_state_parent']['mount'],('target storage',mount_info))
    sealed=b['prerequisite_sha256'];need(set(sealed)==set(b['prerequisite_rc']+b['prerequisite_json']) and all(sha(Path(n))==v for n,v in sealed.items()),'copied H2 prerequisite bytes')
    need(source_clean()==host['source_index_sha256'],'wrong staged Ruff source')

if __name__=='__main__':
    b=load(H/'runner-binding.json'); check_h3(b)
    for a in b['arms'].values():
        for k in ('cargo','driver'):need(sha(Path(a[k]))==a[k+'_sha256'],k)
    for tool,v in b['host']['host_tools'].items():need(Path(v['path']).resolve()==Path(v['resolved']) and sha(Path(v['path']))==v['sha256'],tool)
    need(not Path(b['storage']['new_result_path']).exists(),'expected empty initial H3 result')
    print('Exact staged host, source index, release images, and 14 successful previous receipts. Capacity:',gate_free(BASE,b['storage']['expected_increment_bytes'])/2**30,'GiB. No native commands run.')
