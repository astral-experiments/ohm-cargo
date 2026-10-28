from snapshot import *
import time
wait=Y/'receipts/cold-current/exit.json'
while not wait.exists():time.sleep(5)
def report(n):print(n,flush=True);return snapshot(n)
def apply(rev):
 a=['git','apply'];extra=['--reverse'] if rev else [];sp.run([*a,'--check',*extra,Y/'change.patch'],check=True,cwd=W);sp.run([*a,*extra,Y/'change.patch'],check=True,cwd=W); commit=OLD if rev else H; assert sp.run(['git','diff','--quiet',commit,'--'],cwd=W).returncode==0

def equivalent(actual,expected):
 assert actual['external_output']==expected['external_output'] and actual['cli_lines']==expected['cli_lines'] and actual['complete_cli_json_sha256']==expected['complete_cli_json_sha256'],(actual,expected)
original=report('cold-current');phase('settle-current');settled=report('settle-current');equivalent(settled,original)
apply(True);phase('warm-reverse');edited=report('warm-reverse');assert original['external_output']!=edited['external_output'] and original['cli_lines']!=edited['cli_lines'];phase('unchanged-reverse');repeated=report('unchanged-reverse');equivalent(edited,repeated)
P.rename(Y/'states/warm');newstate();phase('clean-reverse');clean=report('clean-reverse');equivalent(edited,clean);P.rename(Y/'states/independent-clean');(Y/'states/warm').rename(P)
apply(False);phase('restored');rest=report('restored');equivalent(rest,original);phase('unchanged-restored');after=report('unchanged-restored');equivalent(after,original);write(Y/'terminal.json',{'success':True,'phases':['cold-current','settle-current','warm-reverse','unchanged-reverse','clean-reverse','restored','unchanged-restored'],'original':original,'edited':edited,'clean':clean,'restored':rest,'stock':RELEASE_CARGO})
