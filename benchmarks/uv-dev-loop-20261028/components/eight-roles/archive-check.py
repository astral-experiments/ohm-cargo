"""Validate the result archive from a new directory with Python isolated from site packages."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,zipfile
root=Path(__file__).resolve().parent
def checksum(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
archive=root/'evidence.zip'
with tempfile.TemporaryDirectory(prefix='ohm-eight-public-verify-') as tmp:
    tmp=Path(tmp)
    with zipfile.ZipFile(archive) as z:
        for m in z.infolist():
            assert Path(m.filename).is_relative_to('.') and '..' not in Path(m.filename).parts
        z.extractall(tmp);n=len(z.namelist())
    cmd=[sys.executable,'-I','-S',str(tmp/'verify.py'),str(tmp)]
    r=subprocess.run(cmd,cwd=tmp,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    actual=json.loads(r.stdout);previous=json.loads((root/'portable-summary.json').read_text());assert actual==previous
    result={'archive':archive.name,'archive_size':archive.stat().st_size,'archive_entries':n,'archive_sha256':checksum(archive),'isolated_python_flags':['-I','-S'],'qualifies':actual['joint_qualification'],'same_as_live_raw_receipts':True,'verifier_sha256':checksum(tmp/'verify.py'),'portable_summary_sha256':checksum(root/'portable-summary.json')}
    (root/'archive-integrity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
