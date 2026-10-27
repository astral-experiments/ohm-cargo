"""Add a source-matched fixed-width full-link arm without changing the original A/C relative orders."""
import hashlib,itertools,json,random
from pathlib import Path
p=Path(__file__).resolve().parent;start=p/'prospective.json';source=json.loads(start.read_bytes());assert hashlib.sha256(start.read_bytes()).hexdigest()=='0b07e992ac7a455bdeb5c6ad749e00bec8b91f4430e5247d9c9af8251c2e30f7'
from collections import Counter
orders={}
for k,v in source['endpoints'].items():
 pair=[['A' if name=='parent' else 'C' for name in row] for row in v['order']]
 rng=random.Random('A9 matched true fixed width 20261027 placement: '+k)
 slots={orientation:[0,1,2]*3 for orientation in ('A','C')}
 for vals in slots.values():rng.shuffle(vals)
 actual=[]
 for row in pair:
  x=list(row);x.insert(slots[row[0]].pop(),'B');actual.append(x)
 assert [list(filter(lambda a:a!='B',v)) for v in actual]==pair and Counter(map(tuple,actual))=={x:3 for x in itertools.permutations('ABC')}
 orders[k]=actual
# With no semantic source transition, define one separate 18-block descriptive no-work cohort.
q=list(itertools.permutations('ABC'))*3;random.Random('A9 20261027 single declared no-op').shuffle(q);orders['no-op']=[list(v) for v in q]
data=dict(prior_registration_sha256=hashlib.sha256(start.read_bytes()).hexdigest(),host=source['benchmark_host'],pin=source['pin'],
 baseline_rustc=source['both_rustc_driver'],jobs=8,cpu_affinity='0-23',state_device='H4 secondary ext4; each trained arm independently cold with no donor compiler outputs',
 arms={'A':{'cargo':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','source':'d38fdd02503662de04c52f5f370f5dd81bddf868','width':'untouched stock'},
       'B':{'cargo':'991d983a45416c63bc637511ccc584ea2ca6486d1a0b190108577ef00770768f','source':'51dc314de93c2875b91b00a5b67e05323147a97b','width':'first eligible dirty compile trains fixed width; all later eligible builds perform a full real compile + link'},
       'C':{'cargo':'5227d7a8222366077a451f8d08d6e267108e16708db0326275fce212a180cf76','source':'2aebeb50f0170cf20112766c538f34defa018d93','width':'same first training, later certified test rustc+link omitted'}},
 orders=orders,primary_endpoints=list(source['endpoints']),
 analysis='18 blocks x 3, three of every ordering per endpoint, A/C relative order copied from the published initial plan. Compare C:A and C:B using the conditional two-sided randomization distribution of mean paired log wall time with the remaining arm position held fixed. Each of three strata contributes 20 assignments, for 8000. Holm across six tests, all results reported. Report arm medians, geometric reductions, bootstrap intervals, favorable direction count, descriptive B:A and unchanged endpoint; never count the upstream jobs that are still run as zero.',
 precedence='Source and the three full historical patches were chosen before scoring. No raw ELF normalization in the eligible B, C and forced C cohorts. A against B/C may differ in the known .rodata header and build-ID because the fixed width is a distinct input; show exact all-ELF decomposition, claim only what is unchanged. Before starting verify the cold and first training costs and field/list equality on each independently cold arm, normal/true native negative controls, current helper/frontend and wrapper eligibility, competing-workload absence and measured output roster. No score from failed setup. No source mutations to shared Ruff.',
 secondary='Report unscored transition times (cold, first dirty, matched forced) with traced process classes and exact command. Fresh-command timing is a separate descriptive 18-block family at the fully trained original stdlib source. Report B:A including native proof checks and fixed-width cost on all primary commands. The prior 374-unit both-package command and active/failing tests are separate mechanistic controls. Significant gains require favorable C vs A and vs B, no correctness failure, favorable independently replicated evidence, and adjusted P<0.05 on the registered workspace family.',
 command=source['cmd'],edits={k:{x:v[x] for x in ('full_commit','parent_commit','patch_sha256','paths')} for k,v in source['endpoints'].items()})
dst=p/'fixed-width-plan.json'
if dst.exists():assert json.loads(dst.read_bytes())==data
else:dst.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
print(hashlib.sha256(dst.read_bytes()).hexdigest())
