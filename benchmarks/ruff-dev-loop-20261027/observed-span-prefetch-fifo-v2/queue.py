"""Separate unscored qualification and the future scored execution, each under its explicit immutable grant."""
from pathlib import Path
import json,subprocess,sys,traceback
h=Path(__file__).resolve().parent;b=h.parent;out=b/'whole-ruff-observer-prefetch-fifo-v2'
phase,grant=sys.argv[1:];assert phase in ('anchors','score')
def marker(name,strval):
    where=h/name;assert not where.exists();where.write_text(strval+'\n')
try:
    assert (b/'prefetch-fifo-qualified/queue.rc').read_text().strip()=='1'
    assert (b/'cargo-observer-fifo-qualification/queue.rc').read_text().strip()=='0'
    assert not list((b/'whole-ruff-observer-prefetch-fifo-v1').glob('timed-*'))
    if phase=='score':assert (h/'anchors.rc').read_text().strip()=='0' and (out/'anchors-complete.json').is_file()
    sha='dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
    subprocess.run(['taskset','-c','0-23',sys.executable,'-B',h/'run.py','--phase',phase,'--release',grant,'--subjects',b/'prefetch-fifo-qualified/subjects','--driver',b/('drivers/driver-'+sha),'--out',out],check=True)
    if phase=='score':subprocess.run(['taskset','-c','24-31',sys.executable,'-B',h/'analyze.py','--raw',out,'--public',out/'public'],check=True)
    marker('anchors.rc' if phase=='anchors' else 'queue.rc','0')
except BaseException:
    (h/(phase+'-error.txt')).write_text(traceback.format_exc());marker('anchors.rc' if phase=='anchors' else 'queue.rc','1');raise
