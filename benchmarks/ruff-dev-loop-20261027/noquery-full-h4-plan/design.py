"""Registered four-arm cold transitions and disjointly randomized settled commands."""
from itertools import permutations
import random

ARMS='OABC'
HISTORIES=24
WAVES=12
COLD_SEED=202610280817
SETTLED_SEED=202610280819


def schedule():
    cold=[''.join(p) for p in permutations(ARMS)]
    random.Random(COLD_SEED).shuffle(cold)
    rng=random.Random(SETTLED_SEED);histories=[]
    for number,order in enumerate(cold,1):
        waves=[]
        for _ in range(WAVES//4):
            cycle=list(ARMS);rng.shuffle(cycle)
            rotations=[''.join(cycle[i:]+cycle[:i]) for i in range(4)]
            rng.shuffle(rotations);waves+=rotations
        for arm in ARMS:
            assert [sum(w[slot]==arm for w in waves) for slot in range(4)]==[3]*4
        histories.append({'history':number,'cold_order':order,'settled_orders':waves})
    assert sorted(cold)==sorted(''.join(p) for p in permutations(ARMS))
    return histories
