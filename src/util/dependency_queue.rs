//! A graph-like structure used to represent a set of dependencies and in what
//! order they should be built.
//!
//! This structure is used to store the dependency graph and dynamically update
//! it to figure out when a dependency should be built.
//!
//! Dependencies in this queue are represented as a (node, edge) pair. This is
//! used to model nodes which produce multiple outputs at different times but
//! some nodes may only require one of the outputs and can start before the
//! whole node is finished.

use crate::util::data_structures::{HashMap, HashSet};
use std::collections::BinaryHeap;
use std::hash::Hash;

#[derive(Debug)]
pub struct DependencyQueue<N: Hash + Eq, E: Hash + Eq, V> {
    indices: HashMap<N, usize>,
    nodes: Vec<Node<N, E, V>>,
    ready: BinaryHeap<(usize, usize)>,
    remaining: usize,
}

#[derive(Debug)]
struct Node<N, E, V> {
    key: N,
    value: Option<V>,
    /// Number of distinct producer/artifact pairs that have not finished.
    pending: usize,
    /// Consumers waiting for each artifact produced by this node.
    dependents: HashMap<E, Vec<usize>>,
    cost: usize,
    priority: usize,
}

impl<N: Hash + Eq, E: Hash + Eq, V> Default for DependencyQueue<N, E, V> {
    fn default() -> Self {
        Self::new()
    }
}

impl<N: Hash + Eq, E: Hash + Eq, V> DependencyQueue<N, E, V> {
    /// Creates an empty dependency queue.
    pub fn new() -> Self {
        Self {
            indices: HashMap::default(),
            nodes: Vec::new(),
            ready: BinaryHeap::new(),
            remaining: 0,
        }
    }
}

impl<N: Hash + Eq + Clone, E: Eq + Hash + Clone, V> DependencyQueue<N, E, V> {
    /// Assigns an index even when a dependency is mentioned before it is queued.
    fn index(&mut self, key: N) -> usize {
        let next = self.nodes.len();
        *self.indices.entry(key.clone()).or_insert_with(|| {
            self.nodes.push(Node {
                key,
                value: None,
                pending: 0,
                dependents: HashMap::default(),
                cost: 0,
                priority: 0,
            });
            next
        })
    }

    /// Adds a job and the producer/artifact pairs it must wait for.
    pub fn queue(
        &mut self,
        key: N,
        value: V,
        dependencies: impl IntoIterator<Item = (N, E)>,
        cost: usize,
    ) {
        let index = self.index(key);
        assert!(self.nodes[index].value.is_none());
        let mut unique = HashSet::default();
        for (dependency, edge) in dependencies {
            let dependency = self.index(dependency);
            if unique.insert((dependency, edge.clone())) {
                self.nodes[dependency]
                    .dependents
                    .entry(edge)
                    .or_default()
                    .push(index);
            }
        }
        self.nodes[index].pending = unique.len();
        self.nodes[index].value = Some(value);
        self.nodes[index].cost = cost;
        self.remaining += 1;
    }

    /// Computes priorities after the graph is complete and prepares its ready jobs.
    pub fn queue_finished(&mut self) {
        assert!(self.nodes.iter().all(|node| node.value.is_some()));
        let len = self.nodes.len();
        let mut state = vec![0_u8; len];
        // Store only occupied bitmap words, so unrelated small components do not
        // allocate full graph-sized bitmaps. Leaves need no bitmap at all.
        let mut reachable: Vec<Option<Vec<(usize, usize)>>> = vec![None; len];
        let mut bits = HashMap::<usize, usize>::default();
        let mut stack = Vec::new();
        for root in 0..len {
            stack.push((root, false));
            while let Some((index, visited)) = stack.pop() {
                if visited {
                    let node = &self.nodes[index];
                    let priority = if node.dependents.is_empty() {
                        node.cost + node.cost
                    } else {
                        bits.clear();
                        bits.insert(
                            index / usize::BITS as usize,
                            1 << (index % usize::BITS as usize),
                        );
                        for &dependent in node.dependents.values().flatten() {
                            if let Some(dependent_bits) = &reachable[dependent] {
                                for &(word, other) in dependent_bits {
                                    *bits.entry(word).or_default() |= other;
                                }
                            } else {
                                *bits.entry(dependent / usize::BITS as usize).or_default() |=
                                    1 << (dependent % usize::BITS as usize);
                            }
                        }
                        // Preserve the existing priority: own cost plus the costs of
                        // the transitive dependent set, which includes this node.
                        let mut priority = node.cost;
                        for (&word_index, &word) in &bits {
                            let mut word = word;
                            while word != 0 {
                                let dependent = word_index * usize::BITS as usize
                                    + word.trailing_zeros() as usize;
                                priority += self.nodes[dependent].cost;
                                word &= word - 1;
                            }
                        }
                        reachable[index] =
                            Some(bits.iter().map(|(&word, &bits)| (word, bits)).collect());
                        priority
                    };
                    self.nodes[index].priority = priority;
                    state[index] = 2;
                } else {
                    match state[index] {
                        2 => continue,
                        1 => panic!("cycle in DependencyQueue"),
                        _ => {}
                    }
                    state[index] = 1;
                    stack.push((index, true));
                    for &dependent in self.nodes[index].dependents.values().flatten() {
                        stack.push((dependent, false));
                    }
                }
            }
        }
        self.ready = self
            .nodes
            .iter()
            .enumerate()
            .filter(|(_, node)| node.pending == 0)
            .map(|(index, node)| (node.priority, index))
            .collect();
    }

    /// Takes a ready job with the highest priority.
    pub fn dequeue(&mut self) -> Option<(N, V, usize)> {
        let (priority, index) = self.ready.pop()?;
        let node = &mut self.nodes[index];
        let value = node.value.take().expect("ready job was already dequeued");
        self.remaining -= 1;
        Some((node.key.clone(), value, priority))
    }

    /// Returns whether all jobs have been dequeued.
    pub fn is_empty(&self) -> bool {
        self.remaining == 0
    }

    /// Returns the number of jobs that have not been dequeued.
    pub fn len(&self) -> usize {
        self.remaining
    }

    /// Records one producer/artifact completion and returns newly ready consumers.
    pub fn finish(&mut self, node: &N, edge: &E) -> Vec<&N> {
        let Some(&index) = self.indices.get(node) else {
            return Vec::new();
        };
        let Some(dependents) = self.nodes[index].dependents.remove(edge) else {
            return Vec::new();
        };
        let mut unblocked = Vec::new();
        for dependent in dependents {
            let node = &mut self.nodes[dependent];
            node.pending -= 1;
            if node.pending == 0 {
                self.ready.push((node.priority, dependent));
                unblocked.push(dependent);
            }
        }
        unblocked
            .into_iter()
            .map(|index| &self.nodes[index].key)
            .collect()
    }
}

#[cfg(test)]
mod test {
    use super::DependencyQueue;

    #[test]
    fn deep_first_equal_cost() {
        let mut q = DependencyQueue::new();

        q.queue(1, (), vec![], 1);
        q.queue(2, (), vec![(1, ())], 1);
        q.queue(3, (), vec![], 1);
        q.queue(4, (), vec![(2, ()), (3, ())], 1);
        q.queue(5, (), vec![(4, ()), (3, ())], 1);
        q.queue_finished();

        assert_eq!(q.dequeue(), Some((1, (), 5)));
        assert_eq!(q.dequeue(), Some((3, (), 4)));
        assert_eq!(q.dequeue(), None);
        q.finish(&3, &());
        assert_eq!(q.dequeue(), None);
        q.finish(&1, &());
        assert_eq!(q.dequeue(), Some((2, (), 4)));
        assert_eq!(q.dequeue(), None);
        q.finish(&2, &());
        assert_eq!(q.dequeue(), Some((4, (), 3)));
        assert_eq!(q.dequeue(), None);
        q.finish(&4, &());
        assert_eq!(q.dequeue(), Some((5, (), 2)));
    }

    #[test]
    fn sort_by_highest_cost() {
        let mut q = DependencyQueue::new();

        q.queue(1, (), vec![], 1);
        q.queue(2, (), vec![(1, ())], 1);
        q.queue(3, (), vec![], 4);
        q.queue(4, (), vec![(2, ()), (3, ())], 1);
        q.queue_finished();

        assert_eq!(q.dequeue(), Some((3, (), 9)));
        assert_eq!(q.dequeue(), Some((1, (), 4)));
        assert_eq!(q.dequeue(), None);
        q.finish(&3, &());
        assert_eq!(q.dequeue(), None);
        q.finish(&1, &());
        assert_eq!(q.dequeue(), Some((2, (), 3)));
        assert_eq!(q.dequeue(), None);
        q.finish(&2, &());
        assert_eq!(q.dequeue(), Some((4, (), 2)));
        assert_eq!(q.dequeue(), None);
        q.finish(&4, &());
        assert_eq!(q.dequeue(), None);
    }

    #[test]
    fn artifact_edges_and_duplicate_dependencies() {
        let mut q = DependencyQueue::new();
        // Queue consumers first, and repeat one edge as can happen with shared dependencies.
        q.queue(
            "consumer",
            (),
            [("producer", 0), ("producer", 0), ("producer", 1)],
            1,
        );
        q.queue("metadata-only", (), [("producer", 0)], 1);
        q.queue("producer", (), [], 1);
        q.queue_finished();
        assert_eq!(q.len(), 3);
        assert_eq!(q.dequeue().map(|(key, _, _)| key), Some("producer"));
        assert_eq!(q.dequeue(), None);
        assert_eq!(q.finish(&"producer", &0), [&"metadata-only"]);
        assert_eq!(q.dequeue().map(|(key, _, _)| key), Some("metadata-only"));
        assert_eq!(q.dequeue(), None);
        assert_eq!(q.finish(&"producer", &1), [&"consumer"]);
        assert_eq!(q.dequeue().map(|(key, _, _)| key), Some("consumer"));
        assert!(q.is_empty());
        assert!(q.finish(&"consumer", &0).is_empty());
        assert!(q.finish(&"absent", &0).is_empty());
    }

    #[test]
    fn empty_queue() {
        let mut q = DependencyQueue::<usize, u8, ()>::new();
        q.queue_finished();
        assert!(q.is_empty());
        assert_eq!(q.dequeue(), None);
    }

    #[test]
    #[should_panic(expected = "cycle in DependencyQueue")]
    fn rejects_cycles() {
        let mut q = DependencyQueue::new();
        q.queue(0, (), [(1, ())], 1);
        q.queue(1, (), [(0, ())], 1);
        q.queue_finished();
    }

    #[test]
    fn priorities_and_completions_match_graph_model() {
        // Exercise shared descendants, all artifact kinds, forward references, duplicates,
        // equal priorities, arbitrary completion order, and multiple bitmap words.
        for seed in 1..=80_u64 {
            let mut random = seed;
            let mut next = || {
                random = random.wrapping_mul(6364136223846793005).wrapping_add(1);
                (random >> 32) as usize
            };
            let len = if seed <= 3 {
                [1, 65, 129][seed as usize - 1]
            } else {
                next() % 48 + 1
            };
            let costs: Vec<_> = (0..len).map(|_| next() % 7 + 1).collect();
            let mut dependencies = vec![Vec::new(); len];
            for (consumer, inputs) in dependencies.iter_mut().enumerate() {
                for producer in 0..consumer {
                    if next() % 8 == 0 {
                        inputs.push((producer, (next() % 3) as u8));
                        if next() % 3 == 0 {
                            inputs.push((producer, (next() % 3) as u8));
                        }
                    }
                }
                inputs.sort_unstable();
                inputs.dedup();
            }
            let priorities: Vec<_> = (0..len)
                .map(|producer| {
                    let mut reached = vec![false; len];
                    reached[producer] = true;
                    for consumer in producer + 1..len {
                        reached[consumer] = dependencies[consumer]
                            .iter()
                            .any(|&(input, _)| reached[input]);
                    }
                    costs[producer]
                        + reached
                            .iter()
                            .zip(&costs)
                            .filter_map(|(reached, cost)| reached.then_some(cost))
                            .sum::<usize>()
                })
                .collect();
            let mut q = DependencyQueue::new();
            for node in (0..len).rev() {
                q.queue(
                    node,
                    node,
                    dependencies[node]
                        .iter()
                        .copied()
                        .chain(dependencies[node].first().copied()),
                    costs[node],
                );
            }
            q.queue_finished();
            let mut pending = dependencies.clone();
            let mut started = vec![false; len];
            let mut events = Vec::new();
            loop {
                let best = (0..len)
                    .filter(|&node| !started[node] && pending[node].is_empty())
                    .map(|node| priorities[node])
                    .max();
                if let Some(best) = best {
                    let (node, value, priority) = q.dequeue().expect("ready model node");
                    assert!(!started[node] && pending[node].is_empty());
                    assert_eq!((value, priority), (node, best));
                    started[node] = true;
                    events.extend((0..3).map(|edge| (node, edge)));
                    assert_eq!(q.len(), started.iter().filter(|&&value| !value).count());
                } else {
                    assert_eq!(q.dequeue(), None);
                    if events.is_empty() {
                        break;
                    }
                    let event = events.swap_remove(next() % events.len());
                    let mut expected = Vec::new();
                    for (node, inputs) in pending.iter_mut().enumerate() {
                        if let Some(index) = inputs.iter().position(|input| *input == event) {
                            inputs.swap_remove(index);
                            if inputs.is_empty() {
                                expected.push(node);
                            }
                        }
                    }
                    let mut actual: Vec<_> =
                        q.finish(&event.0, &event.1).into_iter().copied().collect();
                    actual.sort_unstable();
                    assert_eq!(actual, expected);
                }
            }
            assert!(q.is_empty() && started.iter().all(|&value| value));
        }
    }

    #[test]
    fn many_disconnected_pairs() {
        let mut q = DependencyQueue::new();
        for node in 0..20_000 {
            q.queue(
                node,
                (),
                if node % 2 == 1 {
                    Some((node - 1, ()))
                } else {
                    None
                },
                1,
            );
        }
        q.queue_finished();
        let mut count = 0;
        while let Some((node, (), priority)) = q.dequeue() {
            assert_eq!(priority, if node % 2 == 0 { 3 } else { 2 });
            q.finish(&node, &());
            count += 1;
        }
        assert_eq!(count, 20_000);
        assert!(q.is_empty());
    }
}
