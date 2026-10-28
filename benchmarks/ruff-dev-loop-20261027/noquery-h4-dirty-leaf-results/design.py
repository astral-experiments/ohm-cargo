"""Provisional design. An independently verified binding and approval precede all timing."""
from itertools import permutations
import json
import random

ARMS = 'BPN'
NOMINAL = 'XYZ'
CLUSTERS = 24
CYCLES = {'check': 66, 'build': 6}
POSITION_SEED = 433517654
ASSIGNMENT_SEED = 102728303


def schedule():
    nominal_orders = [''.join(p) for p in permutations(NOMINAL)]
    rng = random.Random(POSITION_SEED)
    # Each group of three rotations puts every arm once in each physical slot.
    # Alternate the two rotation orbits to balance directional carryover as well.
    orbits = [[p[i:] + p[:i] for i in range(3)] for p in ('XYZ', 'XZY')]
    start_orbit = {(k, d): rng.randrange(2) for k in CYCLES for d in ('edit', 'restore')}

    assignments = [''.join(p) for p in permutations(ARMS)] * (CLUSTERS // 6)
    random.Random(ASSIGNMENT_SEED).shuffle(assignments)
    blocks = []
    for index, assignment in enumerate(assignments):
        by_kind = {}
        for kind, n in CYCLES.items():
            order_by_direction = []
            for direction in ('edit', 'restore'):
                per_direction = nominal_orders * ((n // 2) // 6)
                per_direction += orbits[(index + start_orbit[kind, direction]) % 2]
                assert len(per_direction) == n // 2
                rng.shuffle(per_direction)
                order_by_direction.append(per_direction)
            by_kind[kind] = []
            for i in range(n):
                nominal = order_by_direction[i % 2][i // 2]
                by_kind[kind].append({
                    'kind': kind, 'cycle': i + 1,
                    'direction': 'restore' if i % 2 else 'edit', 'nominal': nominal,
                    'order': ''.join(assignment[NOMINAL.index(slot)] for slot in nominal),
                })

        # Every run of twelve cycles contains eleven check cycles and one build cycle.
        cycles = []
        for i in range(CYCLES['build']):
            batch = by_kind['check'][11 * i:11 * i + 11]
            batch.insert(rng.randrange(12), by_kind['build'][i])
            cycles.extend(batch)
        blocks.append({'block': index + 1, 'assignment': assignment, 'cycles': cycles})
    return blocks


if __name__ == '__main__':
    print(json.dumps(schedule(), separators=(',', ':')))
