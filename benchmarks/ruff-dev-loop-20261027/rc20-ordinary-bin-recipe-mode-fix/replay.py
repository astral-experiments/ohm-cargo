"""Run both fixture types and the fixed-path upgrade against exact, caller-supplied Linux images."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

DIGESTS = {
    'released': '789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1',
    'original282': 'ad893345f66ade1c886309b0fc2f98ec5b225d206c176e356531f0e3467eff81',
    'original284': '8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5',
    'fixed': '6d0449d4eb0aa490e04aa553bab278c7818efe2c7d529b1d5c9536f01ef90168',
    'rustc': '5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511',
    'wild': '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5',
}
def hf(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ('fresh', 'signed_sdk', 'original282', 'original284', 'fixed'):
        ap.add_argument(arg,type=Path)
    opts=ap.parse_args()
    out=opts.fresh.resolve()
    if out.exists(): ap.error('fresh must be a new directory')
    if shutil.disk_usage(out.parent).free<=24*2**30+600*2**20: ap.error('reserve 24 GiB plus 600 MiB before starting')
    source=Path(__file__).resolve().parent
    sdk=opts.signed_sdk.resolve(strict=True)
    inputs={'released':sdk/'bin/cargo','rustc':sdk/'bin/rustc','wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}
    inputs.update({k:getattr(opts,k).resolve(strict=True)for k in ('original282','original284','fixed')})
    for name,f in inputs.items():
        if hf(f)!=DIGESTS[name]: ap.error('wrong '+name+' digest')
    out.mkdir(mode=0o700)
    for name,label in [('original282','asm-h4-a8f0c9aa0'),('original284','measured-h4-8dc33c9cc'),('fixed','measured-h4-e2fa457aa')]:
        subject=out/label;subject.mkdir();(subject/'cargo').symlink_to(inputs[name])
    (out/'official19-published-linux-signed').mkdir()
    (out/'official19-published-linux-signed/sdk').symlink_to(sdk,target_is_directory=True)
    fixed_sdk=out/'fixed-sdk';(fixed_sdk/'bin').mkdir(parents=True)
    for name in ('rustc','rustdoc'):
        (fixed_sdk/'bin'/name).symlink_to(sdk/'bin'/name)
    (fixed_sdk/'bin/cargo').symlink_to(inputs['fixed']);(fixed_sdk/'lib').symlink_to(sdk/'lib',target_is_directory=True)
    subprocess.run([sys.executable,'-IB',source/'replay-values.py',fixed_sdk,out/'two-way-values','--expect','correct'],check=True)
    subprocess.run([sys.executable,'-IB',source/'h8-verdict.py',out/'diagnostics',fixed_sdk,DIGESTS['fixed'],DIGESTS['rustc']],check=True)
    shutil.copyfile(source/'qualify-relink-collection-verdict.py',out/'qualify-relink-collection-verdict.py')
    shutil.copyfile(source/'h8-upgrade.py',out/'upgrade.py')
    subprocess.run([sys.executable,'-IB',out/'upgrade.py'],check=True)

if __name__=='__main__':
    main()
