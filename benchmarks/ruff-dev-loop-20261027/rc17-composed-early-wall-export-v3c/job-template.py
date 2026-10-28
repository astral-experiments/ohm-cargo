from pathlib import Path
import subprocess,sys
p=Path(sys.argv[1]);role=sys.argv[2]
with (p/(role+'.out')).open('xb') as so, (p/(role+'.err')).open('xb') as se:
 rc=subprocess.run([sys.executable,'-IB',*sys.argv[3:]],stdout=so,stderr=se).returncode
with (p/(role+'.exit')).open('x') as f: f.write(str(rc))
