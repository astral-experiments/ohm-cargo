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
use std::hash::Hash;

#[derive(Debug)]
pub struct DependencyQueue<N: Hash + Eq, E: Hash + Eq, V> {
    /// A list of all known keys to build.
    ///
    /// The value of the hash map is list of dependencies which still need to be
    /// built before the package can be built. Note that the set is dynamically
    /// updated as more dependencies are built.
    dep_map: HashMap<N, (HashSet<(N, E)>, V)>,

    /// A reverse mapping of a package to all packages that depend on that
    /// package.
    ///
    /// This map is statically known and does not get updated throughout the
    /// lifecycle of the `DependencyQueue`.
    ///
    /// This is sort of like a `HashMap<(N, E), HashSet<N>>` map, but more
    /// easily indexable with just an `N`
    reverse_dep_map: HashMap<N, HashMap<E, HashSet<N>>>,

    /// The relative priority of this package. Higher values should be scheduled sooner.
    priority: HashMap<N, usize>,

    /// An expected cost for building this package. Used to determine priority.
    cost: HashMap<N, usize>,
}

impl<N: Hash + Eq, E: Hash + Eq, V> Default for DependencyQueue<N, E, V> {
    fn default() -> DependencyQueue<N, E, V> {
        DependencyQueue::new()
    }
}

impl<N: Hash + Eq, E: Hash + Eq, V> DependencyQueue<N, E, V> {
    /// Creates a new dependency queue with 0 packages.
    pub fn new() -> DependencyQueue<N, E, V> {
        DependencyQueue {
            dep_map: HashMap::default(),
            reverse_dep_map: HashMap::default(),
            priority: HashMap::default(),
            cost: HashMap::default(),
        }
    }
}

impl<N: Hash + Eq + Clone, E: Eq + Hash + Clone, V> DependencyQueue<N, E, V> {
    /// Adds a new node and its dependencies to this queue.
    ///
    /// The `key` specified is a new node in the dependency graph, and the node
    /// depend on all the dependencies iterated by `dependencies`. Each
    /// dependency is a node/edge pair, where edges can be thought of as
    /// productions from nodes (aka if it's just `()` it's just waiting for the
    /// node to finish).
    ///
    /// An optional `value` can also be associated with `key` which is reclaimed
    /// when the node is ready to go.
    ///
    /// The cost parameter can be used to hint at the relative cost of building
    /// this node. This implementation does not care about the units of this value, so
    /// the calling code is free to use whatever they'd like. In general, higher cost
    /// nodes are expected to take longer to build.
    pub fn queue(
        &mut self,
        key: N,
        value: V,
        dependencies: impl IntoIterator<Item = (N, E)>,
        cost: usize,
    ) {
        assert!(!self.dep_map.contains_key(&key));

        let mut my_dependencies = HashSet::default();
        for (dep, edge) in dependencies {
            my_dependencies.insert((dep.clone(), edge.clone()));
            self.reverse_dep_map
                .entry(dep)
                .or_insert_with(HashMap::default)
                .entry(edge)
                .or_insert_with(HashSet::default)
                .insert(key.clone());
        }
        self.dep_map.insert(key.clone(), (my_dependencies, value));
        self.cost.insert(key, cost);
    }

    /// All nodes have been added, calculate some internal metadata and prepare
    /// for `dequeue`.
    pub fn queue_finished(&mut self) {
        if let Some(priority) = self.bitset_priorities() {
            self.priority = priority;
            return;
        }

        let mut out = HashMap::default();
        for key in self.dep_map.keys() {
            depth(key, &self.reverse_dep_map, &mut out);
        }
        self.priority = out
            .into_iter()
            .map(|(n, set)| {
                let total_cost =
                    self.cost[&n] + set.iter().map(|key| self.cost[key]).sum::<usize>();
                (n, total_cost)
            })
            .collect();

        /// Creates a flattened reverse dependency list. For a given key, finds the
        /// set of nodes which depend on it, including transitively. This is different
        /// from `self.reverse_dep_map` because `self.reverse_dep_map` only maps one level
        /// of reverse dependencies.
        fn depth<'a, N: Hash + Eq + Clone, E: Hash + Eq + Clone>(
            key: &N,
            map: &HashMap<N, HashMap<E, HashSet<N>>>,
            results: &'a mut HashMap<N, HashSet<N>>,
        ) -> &'a HashSet<N> {
            if results.contains_key(key) {
                let depth = &results[key];
                assert!(!depth.is_empty(), "cycle in DependencyQueue");
                return depth;
            }
            results.insert(key.clone(), HashSet::default());

            let mut set = HashSet::default();
            set.insert(key.clone());

            for dep in map
                .get(key)
                .into_iter()
                .flat_map(|it| it.values())
                .flatten()
            {
                set.extend(depth(dep, map, results).iter().cloned())
            }

            let slot = results.get_mut(key).unwrap();
            *slot = set;
            &*slot
        }
    }

    /// Avoid cloning and hashing nodes while combining small dependency graphs.
    fn bitset_priorities(&self) -> Option<HashMap<N, usize>> {
        let count = self.dep_map.len();
        // Keep the sparse calculation for large graphs and calls made after nodes
        // have been dequeued. At most 512 KiB of bitset words can be allocated,
        // and nodes without reverse dependencies do not need a bitset at all.
        let words = count.div_ceil(64);
        if count == 0 || self.cost.len() != count || count.checked_mul(words)? > 64 * 1024 {
            return None;
        }

        let nodes: Vec<_> = self.dep_map.keys().collect();
        let indices: HashMap<_, _> = nodes.iter().enumerate().map(|(i, &key)| (key, i)).collect();
        let costs: Vec<_> = nodes.iter().map(|key| self.cost[*key]).collect();
        let uniform_cost = costs
            .iter()
            .all(|&cost| cost == costs[0])
            .then_some(costs[0]);
        let mut results = vec![Vec::new(); count];
        let mut state = vec![0; count];
        for i in 0..count {
            depth(
                i,
                &nodes,
                &indices,
                &self.reverse_dep_map,
                &mut results,
                &mut state,
            );
        }

        return Some(
            nodes
                .into_iter()
                .enumerate()
                .map(|(i, key)| {
                    let dependents = if results[i].is_empty() {
                        costs[i]
                    } else if let Some(cost) = uniform_cost {
                        results[i]
                            .iter()
                            .map(|word| word.count_ones() as usize)
                            .sum::<usize>()
                            * cost
                    } else {
                        results[i]
                            .iter()
                            .enumerate()
                            .map(|(word_index, &word)| {
                                let mut word = word;
                                let mut cost = 0;
                                while word != 0 {
                                    cost += costs[word_index * 64 + word.trailing_zeros() as usize];
                                    word &= word - 1;
                                }
                                cost
                            })
                            .sum()
                    };
                    // The closure includes this node; preserve its additional self cost.
                    (key.clone(), costs[i] + dependents)
                })
                .collect(),
        );

        fn depth<N: Hash + Eq, E: Hash + Eq>(
            index: usize,
            nodes: &[&N],
            indices: &HashMap<&N, usize>,
            map: &HashMap<N, HashMap<E, HashSet<N>>>,
            results: &mut [Vec<u64>],
            state: &mut [u8],
        ) {
            assert!(state[index] != 1, "cycle in DependencyQueue");
            if state[index] == 2 {
                return;
            }
            state[index] = 1;
            if let Some(dependents) = map.get(nodes[index]) {
                let mut result = vec![0; nodes.len().div_ceil(64)];
                result[index / 64] |= 1 << (index % 64);
                for dependent in dependents.values().flatten() {
                    let dependent = indices[dependent];
                    depth(dependent, nodes, indices, map, results, state);
                    if results[dependent].is_empty() {
                        result[dependent / 64] |= 1 << (dependent % 64);
                    } else {
                        for (word, &other) in result.iter_mut().zip(&results[dependent]) {
                            *word |= other;
                        }
                    }
                }
                results[index] = result;
            }
            state[index] = 2;
        }
    }

    /// Dequeues a package that is ready to be built.
    ///
    /// A package is ready to be built when it has 0 un-built dependencies. If
    /// `None` is returned then no packages are ready to be built.
    pub fn dequeue(&mut self) -> Option<(N, V, usize)> {
        let (key, priority) = self
            .dep_map
            .iter()
            .filter(|(_, (deps, _))| deps.is_empty())
            .map(|(key, _)| (key.clone(), self.priority[key]))
            .max_by_key(|(_, priority)| *priority)?;
        let (_, data) = self.dep_map.remove(&key).unwrap();
        Some((key, data, priority))
    }

    /// Returns `true` if there are remaining packages to be built.
    pub fn is_empty(&self) -> bool {
        self.dep_map.is_empty()
    }

    /// Returns the number of remaining packages to be built.
    pub fn len(&self) -> usize {
        self.dep_map.len()
    }

    /// Indicate that something has finished.
    ///
    /// Calling this function indicates that the `node` has produced `edge`. All
    /// remaining work items which only depend on this node/edge pair are now
    /// candidates to start their job.
    ///
    /// Returns the nodes that are now allowed to be dequeued as a result of
    /// finishing this node.
    pub fn finish(&mut self, node: &N, edge: &E) -> Vec<&N> {
        // hashset<Node>
        let reverse_deps = self.reverse_dep_map.get(node).and_then(|map| map.get(edge));
        let Some(reverse_deps) = reverse_deps else {
            return Vec::new();
        };
        let key = (node.clone(), edge.clone());
        let mut result = Vec::new();
        for dep in reverse_deps.iter() {
            let edges = &mut self.dep_map.get_mut(dep).unwrap().0;
            assert!(edges.remove(&key));
            if edges.is_empty() {
                result.push(dep);
            }
        }
        result
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
    fn weighted_diamond_with_multiple_artifacts() {
        let mut q = DependencyQueue::new();
        q.queue(0, (), [], 2);
        q.queue(1, (), [(0, 'm'), (0, 'a')], 3);
        q.queue(2, (), [(0, 'm')], 5);
        q.queue(3, (), [(1, 'a'), (2, 'm')], 7);
        q.queue(4, (), [], 11);
        q.queue_finished();

        assert_eq!(q.priority[&0], 19);
        assert_eq!(q.dequeue(), Some((4, (), 22)));
        assert_eq!(q.dequeue(), Some((0, (), 19)));
        q.finish(&0, &'m');
        assert_eq!(q.dequeue(), Some((2, (), 17)));
        assert_eq!(q.dequeue(), None);
        q.finish(&0, &'a');
        assert_eq!(q.dequeue(), Some((1, (), 13)));
        q.finish(&2, &'m');
        assert_eq!(q.dequeue(), None);
        q.finish(&1, &'a');
        assert_eq!(q.dequeue(), Some((3, (), 14)));
    }

    #[test]
    fn priorities_match_reachability() {
        // Every DAG on five ordered nodes, with uniform and nonuniform costs.
        // The oracle uses a boolean transitive closure, independently of the
        // representation and traversal used by queue_finished.
        for mask in 0..1 << 10 {
            for costs in [[100; 5], [1, 0, 7, 3, 0]] {
                let mut q = DependencyQueue::new();
                let mut reachable = [[false; 5]; 5];
                let mut bit = 0;
                for node in 0..5 {
                    let mut dependencies = Vec::new();
                    reachable[node][node] = true;
                    for dependency in 0..node {
                        if mask & (1 << bit) != 0 {
                            dependencies.push((dependency, ()));
                            reachable[dependency][node] = true;
                        }
                        bit += 1;
                    }
                    q.queue(node, (), dependencies, costs[node]);
                }
                for via in 0..5 {
                    for from in 0..5 {
                        for to in 0..5 {
                            reachable[from][to] |= reachable[from][via] && reachable[via][to];
                        }
                    }
                }
                q.queue_finished();
                for node in 0..5 {
                    let expected = costs[node]
                        + (0..5)
                            .filter(|&dependent| reachable[node][dependent])
                            .map(|dependent| costs[dependent])
                            .sum::<usize>();
                    assert_eq!(q.priority[&node], expected, "graph {mask}, node {node}");
                }
            }
        }
    }

    #[test]
    fn priorities_across_bitset_words() {
        for uniform in [false, true] {
            let mut q = DependencyQueue::new();
            let costs: Vec<_> = (0..129)
                .map(|i| if uniform { 100 } else { i % 7 })
                .collect();
            for node in 0usize..129 {
                q.queue(
                    node,
                    (),
                    node.checked_sub(1).map(|dependency| (dependency, ())),
                    costs[node],
                );
            }
            q.queue_finished();
            for node in 0..129 {
                assert_eq!(
                    q.priority[&node],
                    costs[node] + costs[node..].iter().sum::<usize>()
                );
            }
        }
    }

    #[test]
    fn bitset_memory_bound_keeps_sparse_fallback() {
        for count in [2048, 2049] {
            let mut q = DependencyQueue::new();
            q.queue(0, (), [], 1);
            for node in 1..count {
                q.queue(node, (), [(0, ())], 1);
            }
            assert_eq!(q.bitset_priorities().is_some(), count == 2048);
            q.queue_finished();
            assert_eq!(q.priority[&0], count + 1);
            for node in 1..count {
                assert_eq!(q.priority[&node], 2);
            }
        }
    }

    #[test]
    #[should_panic(expected = "cycle in DependencyQueue")]
    fn rejects_cycle() {
        let mut q = DependencyQueue::new();
        q.queue(0, (), [(1, ())], 1);
        q.queue(1, (), [(0, ())], 1);
        q.queue_finished();
    }
}
