"""Use the wall protocol's existing module path, preserving every frozen native source."""
import fcntl, hashlib, json, runpy, sys
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
WALL=P/'wall-protocol-v2';OLD=P/'whole-wild-width-v1';NEW=P/'whole-wild-width-v2'
CONT=P/'whole-wild-width-v2-protocol'
# The frozen v1 worker made this same addition before importing guards.
sys.path.insert(0, str(WALL))


def context():
    assert OLD.samefile(NEW) and (NEW/'tree-before-resume.json').is_file()
    return runpy.run_path(str(CONT/'source/resume.py'),run_name='frozen_native_continuation')

