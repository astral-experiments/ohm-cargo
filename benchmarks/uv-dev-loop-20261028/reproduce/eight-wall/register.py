#!/usr/bin/env python3
"""Freeze both timing schedules before any eight-component fixture is prepared."""
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
plan = dict(uv='c22e6b71933443e9cd299d4b6ac8de035ed4825b',
            command=['test','--no-run','--locked','--offline','-j8'], pairs=24,
            native_cpus=list(range(16)), preparation_cpus=list(range(24,32)),
            rustc_sha256='7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c',
            release_wild_sha256='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5',
            wild_prefix_patch_sha256='a75c1cf2d966ddd1217e33f8879070afe4a9e20ce94d01465a8df109ca69b65c',
            linker_slot='lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd',
            arms={
                'base':{'cargo':['pgo-confirmation-v2/bin/base','51b59d549a21422809d865449be5a4c5b422989b22f7a314c6f18e7ab92b0855'],
                        'wild':['bin/wild-baseline','82a927b86f929b67c58be4d37ab8442f32fcdd115d97334dcc5ac190101d8865']},
                'candidate':{'cargo':['pgo-confirmation-v2/bin/guard-stack','4a61560c17f00e54595122846f5450e7eb6a5ed3da9611ae39f4ecb972ab30d4'],
                             'wild':['wild-prefix-v2/v2-wild','901b68fc9ca30975d837d45dcf1bdf743a6130ecef5e23d6aef44558b09bd7e1']}},
            gate='24 admitted pairs per cohort, positive median reduction and two-sided exact sign p < .05 in each, first cohort rank 7 lower bound > 0',
            cohorts={})
for name,fixture,tag,start,order_seed,edit_seed in (
        ('initial','toolchain-wall','M',10,3110819,431021),
        ('replica','toolchain-wall-replica','Z',40,9905287,730061)):
    order = [('base','candidate'),('candidate','base')]*12
    edits = list(range(start,start+24))
    random.Random(order_seed).shuffle(order)
    random.Random(edit_seed).shuffle(edits)
    plan['cohorts'][name] = dict(fixture=fixture,prefix=tag,order_seed=order_seed,edit_seed=edit_seed,
                                admission_order=['base','candidate'] if name=='initial' else ['candidate','base'],
                                schedule=[dict(literal=f'{tag}{n:02}',arms=arms) for n,arms in zip(edits,order)])
with (HERE/'plan.json').open('x') as f:
    f.write(json.dumps(plan,indent=2)+'\n')
