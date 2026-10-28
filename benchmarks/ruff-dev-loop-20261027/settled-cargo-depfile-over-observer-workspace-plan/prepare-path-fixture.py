"""Bridge the original real-Cargo qualification worker to the independent #261 fixture."""
from pathlib import Path
import prepare
H=prepare.H;P=Path('/mnt/devbox-scratch/dev-user');LOCK=prepare.lock;RT=prepare.sdk;S=prepare.sdk;sha=prepare.sha;save=prepare.store;R=prepare.R;CARGO=prepare.C

def env(mode):
 assert mode in ('library','workspace');return prepare.env()
def cmds(mode):
 assert mode in ('library','workspace');return [prepare.C,'+ohm','build','--locked','--offline','-j4']
def cwd(mode):
 assert mode in ('library','workspace');return prepare.R
