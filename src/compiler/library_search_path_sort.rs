//! Sort dependency directories without repeatedly parsing their common prefix.

use std::mem::size_of;
use std::ops::Range;
use std::path::{Component, PathBuf};

// Bound the requested payload of the component, range, and index allocations.
// Large dependency graphs or paths can always use the original in-place sort.
const MAX_SCRATCH_BYTES: usize = 256 * 1024;

pub(super) fn sort(paths: &mut [PathBuf]) {
    let Some(mut order) = cached_order(paths) else {
        // This must sort the entire original input, including its original tie
        // order. Sorting only an equal-key group need not reproduce it.
        paths.sort_unstable();
        return;
    };

    // The borrowed component keys have been dropped. Follow each permutation
    // cycle, marking its indices as fixed, without another path allocation.
    for start in 0..order.len() {
        let mut current = start;
        loop {
            let next = order[current];
            order[current] = current;
            if next == start {
                break;
            }
            paths.swap(current, next);
            current = next;
        }
    }
}

fn cached_order(paths: &[PathBuf]) -> Option<Vec<usize>> {
    if paths.len() < 2 {
        return None;
    }
    let index_bytes = paths
        .len()
        .checked_mul(size_of::<Range<usize>>() + size_of::<usize>())?;
    let component_limit = MAX_SCRATCH_BYTES.checked_sub(index_bytes)? / size_of::<Component<'_>>();

    // Compare actual components, not byte prefixes or reconstructed suffix
    // Paths: separators, leading dots, and Windows prefixes carry context.
    let mut common_len = usize::MAX;
    for path in &paths[1..] {
        common_len = paths[0]
            .components()
            .zip(path.components())
            .take(common_len)
            .take_while(|(left, right)| left == right)
            .count();
        if common_len == 0 {
            return None;
        }
    }

    let mut component_count = 0usize;
    for path in paths {
        component_count =
            component_count.checked_add(path.components().skip(common_len).count())?;
        if component_count > component_limit {
            return None;
        }
    }

    let mut components = Vec::new();
    components.try_reserve_exact(component_count).ok()?;
    let mut ranges = Vec::new();
    ranges.try_reserve_exact(paths.len()).ok()?;
    let mut order = Vec::new();
    order.try_reserve_exact(paths.len()).ok()?;
    for (index, path) in paths.iter().enumerate() {
        let start = components.len();
        components.extend(path.components().skip(common_len));
        ranges.push(start..components.len());
        order.push(index);
    }

    let key = |index: usize| &components[ranges[index].clone()];
    order.sort_unstable_by(|&left, &right| key(left).cmp(key(right)));

    // Path equality ignores some literal spelling differences. An unstable
    // index sort could permute those ties differently from PathBuf's sort.
    // Keep the original input untouched until every tied group is byte-equal.
    if order.windows(2).any(|pair| {
        key(pair[0]) == key(pair[1])
            && paths[pair[0]].as_os_str().as_encoded_bytes()
                != paths[pair[1]].as_os_str().as_encoded_bytes()
    }) {
        return None;
    }
    Some(order)
}

#[cfg(test)]
mod tests {
    use super::{MAX_SCRATCH_BYTES, cached_order, sort};
    use std::ffi::OsString;
    use std::mem::size_of;
    use std::ops::Range;
    use std::path::{Component, PathBuf};

    fn paths(values: &[&str]) -> Vec<PathBuf> {
        values.iter().map(PathBuf::from).collect()
    }

    // This is the original lib_search_paths emission. OsString equality checks
    // every flag, path spelling, position, and duplicate, unlike Path equality.
    fn dependency_args(paths: Vec<PathBuf>) -> Vec<OsString> {
        paths
            .into_iter()
            .flat_map(|path| {
                let mut value = OsString::from("dependency=");
                value.push(path);
                [OsString::from("-L"), value]
            })
            .collect()
    }

    fn assert_original_args(mut input: Vec<PathBuf>) {
        let mut original = input.clone();
        original.sort_unstable();
        let expected = dependency_args(original);
        sort(&mut input);
        assert_eq!(dependency_args(input), expected);
    }

    fn all_permutations(input: &mut [PathBuf], start: usize, cached: bool) {
        if start == input.len() {
            assert_eq!(cached_order(input).is_some(), cached);
            assert_original_args(input.to_vec());
            return;
        }
        for next in start..input.len() {
            input.swap(start, next);
            all_permutations(input, start + 1, cached);
            input.swap(start, next);
        }
    }

    #[test]
    fn non_involutive_cycles_move_paths_in_the_correct_direction() {
        let three = paths(&["/root/b", "/root/c", "/root/a"]);
        assert_eq!(cached_order(&three).unwrap(), [2, 0, 1]);
        assert_original_args(three);

        let seven = paths(&[
            "/root/g", "/root/a", "/root/b", "/root/c", "/root/d", "/root/e", "/root/f",
        ]);
        assert_eq!(cached_order(&seven).unwrap(), [1, 2, 3, 4, 5, 6, 0]);
        assert_original_args(seven);
    }

    #[test]
    fn all_permutations_preserve_order_and_identical_duplicates() {
        let mut input = paths(&[
            "/build/root/pkg/out",
            "/build/root/pkg-long/out",
            "/build/root/pkg",
            "/build/root/../parent/out",
            "/build/root/z/out",
            "/build/root/pkg/out",
        ]);
        all_permutations(&mut input, 0, true);
    }

    #[test]
    fn all_permutations_of_byte_distinct_ties_use_the_original_sort() {
        let mut input = paths(&[
            "/build/root/a//b",
            "/build/root/a/b",
            "/build/root/c/out",
            "/build/root/./a/b",
            "/build/root/a/b/",
            "/build/root/a/b/.",
        ]);
        all_permutations(&mut input, 0, false);
    }

    #[test]
    fn large_mixed_tie_groups_keep_the_complete_original_order() {
        let mut input: Vec<_> = (0..48)
            .rev()
            .map(|index| PathBuf::from(format!("/root/pkg-{index}/out")))
            .collect();
        input.extend(paths(&[
            "/root/pkg-7//out",
            "/root/./pkg-7/out",
            "/root/pkg-7/out/",
            "/root/pkg-23/out/.",
            "/root/pkg-23/out",
        ]));
        for _ in 0..input.len() {
            assert!(cached_order(&input).is_none());
            assert_original_args(input.clone());
            input.rotate_left(1);
        }
    }

    #[test]
    fn common_prefix_uses_components_and_preserves_literal_spellings() {
        for input in [
            paths(&["/tmp//root/a", "/tmp/root/./b", "/tmp/root/c/"]),
            paths(&["./root/a", "./root/./b", "./root/b/.."]),
            paths(&["/tmp/foo", "/tmp/foo-bar", "/tmp/foo/a", "/tmp/foo.bar"]),
            paths(&["/root/é/out", "/root/δ/out", "/root/e\u{301}/out"]),
            paths(&["/", "/a", "/a/b", "/a/b/.."]),
        ] {
            assert!(cached_order(&input).is_some());
            assert_original_args(input);
        }
    }

    #[test]
    fn empty_component_tails_still_distinguish_literal_aliases() {
        let identical = paths(&["/root/pkg/out", "/root/pkg/out", "/root/pkg/out"]);
        assert!(cached_order(&identical).is_some());
        assert_original_args(identical);

        let aliases = paths(&["/root/pkg/out", "/root//pkg/./out", "/root/pkg/out/"]);
        assert!(cached_order(&aliases).is_none());
        assert_original_args(aliases);
    }

    #[test]
    fn absent_prefix_and_small_inputs_preserve_the_original_arguments() {
        for input in [
            vec![],
            paths(&[""]),
            paths(&["/one/path"]),
            paths(&["", "a", "./a", ".", "..", "../a"]),
            paths(&["relative/a", "other/b", "/absolute/c"]),
        ] {
            assert!(cached_order(&input).is_none());
            assert_original_args(input);
        }
    }

    #[test]
    fn range_and_index_budget_falls_back_without_losing_duplicates() {
        let count = MAX_SCRATCH_BYTES / (size_of::<Range<usize>>() + size_of::<usize>()) + 1;
        let input = vec![PathBuf::from("/root/pkg/out"); count];
        assert!(cached_order(&input).is_none());
        assert_original_args(input);
    }

    #[test]
    fn component_budget_falls_back_before_allocating_keys() {
        let count = MAX_SCRATCH_BYTES / size_of::<Component<'_>>() + 1;
        let tail = "component/".repeat(count);
        let input = vec![
            PathBuf::from(format!("/root/a/{tail}")),
            PathBuf::from(format!("/root/b/{tail}")),
        ];
        assert!(cached_order(&input).is_none());
        assert_original_args(input);
    }

    #[cfg(unix)]
    #[test]
    fn non_utf8_components_and_aliases_preserve_exact_bytes() {
        use std::os::unix::ffi::OsStringExt;

        let mut input: Vec<_> = [
            b"/root/\xff/out".as_slice(),
            b"/root/\xfe/out".as_slice(),
            b"/root/\xff-long/out".as_slice(),
        ]
        .into_iter()
        .map(|value| PathBuf::from(OsString::from_vec(value.to_vec())))
        .collect();
        assert!(cached_order(&input).is_some());
        assert_original_args(input.clone());
        input.push(PathBuf::from(OsString::from_vec(
            b"/root//\xff/./out".to_vec(),
        )));
        assert!(cached_order(&input).is_none());
        assert_original_args(input);
    }

    #[cfg(windows)]
    #[test]
    fn windows_prefixes_separators_and_verbatim_dots_keep_path_order() {
        for input in [
            paths(&[r"C:\root\pkg", "C:/root/pkg-long", r"C:\root\pkg\child"]),
            paths(&[r"\\server\share\root\a", r"\\server\share\root\b"]),
            paths(&[r"\\?\C:\root\.\a", r"\\?\C:\root\a", r"\\?\C:\root\..\a"]),
            paths(&[
                r"\\?\UNC\server\share\root\a",
                r"\\?\UNC\server\share\root\b",
            ]),
        ] {
            assert!(cached_order(&input).is_some());
            assert_original_args(input);
        }
        let aliases = paths(&[r"C:\root\pkg", "C:/root/pkg", r"C:\root\\pkg"]);
        assert!(cached_order(&aliases).is_none());
        assert_original_args(aliases);
        assert_original_args(paths(&[r"C:\root\a", r"D:\root\a", r"\\server\share\a"]));
    }

    #[cfg(windows)]
    #[test]
    fn unpaired_windows_surrogates_preserve_original_arguments() {
        use std::os::windows::ffi::OsStringExt;

        let input: Vec<_> = [0xd800, 0xd801, 0xdc00]
            .into_iter()
            .map(|value| {
                let mut wide: Vec<_> = "C:\\root\\".encode_utf16().collect();
                wide.push(value);
                wide.extend("\\out".encode_utf16());
                PathBuf::from(OsString::from_wide(&wide))
            })
            .collect();
        assert!(cached_order(&input).is_some());
        assert_original_args(input);
    }
}
