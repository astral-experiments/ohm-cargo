//! This module handles the locking logic during compilation.

use crate::util::flock;
use crate::{
    CargoResult,
    compiler::{BuildRunner, Unit, UnitIndex},
    util::{FileLock, Filesystem},
};

use crate::util::data_structures::{HashMap, HashSet};
use anyhow::bail;
use std::{
    fmt::{Display, Formatter},
    path::PathBuf,
    sync::{OnceLock, RwLock},
};
#[cfg(unix)]
use std::{fs::File, sync::Arc};
use tracing::instrument;

/// A struct to store the lock handles for build units during compilation.
pub struct LockManager {
    locks: RwLock<HashMap<LockKey, UnitLock>>,
    shared_unit_keys: OnceLock<HashMap<UnitIndex, LockKey>>,
}

enum UnitLock {
    Dynamic(FileLock),
    /// A shared-cache lease is acquired before preparation and never converted.
    Reserved {
        #[cfg(unix)]
        file: Arc<File>,
        #[cfg(not(unix))]
        #[expect(
            dead_code,
            reason = "the guard holds the reserved lock until the build ends"
        )]
        file: FileLock,
        exclusive: bool,
    },
}

impl LockManager {
    pub fn new() -> Self {
        Self {
            locks: RwLock::new(HashMap::default()),
            shared_unit_keys: OnceLock::new(),
        }
    }

    /// Reserves the complete shared graph in canonical path order before observing outputs.
    ///
    /// Requests never change mode while held. If preparation discovers another writer, the
    /// caller must discard the runner and reserve a new set, preserving this global order.
    pub(super) fn reserve_shared_cache(
        &self,
        build_runner: &BuildRunner<'_, '_>,
        exclusive: &HashSet<UnitIndex>,
    ) -> CargoResult<()> {
        if !build_runner.bcx.ws.shared_registry_cache_enabled() {
            return Ok(());
        }
        let mut canonical_profiles = HashMap::default();
        let mut units = build_runner
            .bcx
            .unit_graph
            .keys()
            .filter(|unit| build_runner.files().is_shared_registry_unit(unit))
            .map(|unit| {
                let path = build_runner.files().build_unit_lock(unit);
                let key = LockKey(build_runner.bcx.ws.canonical_build_path(&path));
                let profile = build_runner
                    .files()
                    .layout(unit.kind)
                    .build_dir()
                    .shared_build()
                    .expect("shared registry units have a shared build directory")
                    .parent()
                    .unwrap();
                let canonical_profile = canonical_profiles
                    .entry(unit.kind)
                    .or_insert_with(|| build_runner.bcx.ws.canonical_build_path(profile));
                let expected = canonical_profile.join(path.strip_prefix(profile).unwrap());
                if key.0 != expected {
                    bail!(
                        "shared registry unit lock escapes its locked build profile or namespace: {}; \
                         use a shared build directory without registry subtree aliases",
                        key.0.display()
                    );
                }
                Ok((unit, key))
            })
            .collect::<CargoResult<Vec<_>>>()?;
        let keys = units
            .iter()
            .map(|(unit, key)| (build_runner.bcx.unit_to_index[unit], key.clone()))
            .collect::<HashMap<_, _>>();
        let exclusive = keys
            .iter()
            .filter(|(index, _)| exclusive.contains(index))
            .map(|(_, key)| key)
            .collect::<HashSet<_>>();
        units.sort_unstable_by(|(_, left), (_, right)| left.cmp(right));
        units.dedup_by(|(_, left), (_, right)| left == right);

        #[cfg(unix)]
        Self::reserve_descriptor_budget(build_runner.bcx.unit_graph.len());
        let mut locks = self.locks.write().unwrap();
        assert!(
            locks.is_empty(),
            "shared leases must precede other unit locks"
        );
        for (unit, key) in units {
            let fs = Filesystem::new(key.0.clone());
            let lock_msg = format!(
                "{} ({})",
                unit.pkg.name(),
                build_runner.files().unit_hash(unit)
            );
            let exclusive = exclusive.contains(&key);
            let file = if exclusive {
                fs.open_rw_exclusive_create(&key.0, build_runner.bcx.gctx, &lock_msg)?
            } else {
                fs.open_ro_shared_create(&key.0, build_runner.bcx.gctx, &lock_msg)?
            };
            #[cfg(unix)]
            let file = Arc::new(file.into_file());
            locks.insert(key, UnitLock::Reserved { file, exclusive });
        }
        self.shared_unit_keys
            .set(keys)
            .expect("shared leases must only be prepared once");
        Ok(())
    }

    /// Returns the reserved physical key, including aliases, or an ordinary private key.
    pub(super) fn key_for_unit(&self, build_runner: &BuildRunner<'_, '_>, unit: &Unit) -> LockKey {
        self.shared_unit_keys
            .get()
            .and_then(|keys| keys.get(&build_runner.bcx.unit_to_index[unit]))
            .cloned()
            .unwrap_or_else(|| LockKey::from_unit(build_runner, unit))
    }

    pub(super) fn has_shared_cache_write_access(&self, key: &LockKey) -> bool {
        matches!(
            self.locks.read().unwrap().get(key),
            Some(UnitLock::Reserved {
                exclusive: true,
                ..
            })
        )
    }

    /// Retains the same unit leases in workers that can outlive the Cargo process.
    #[cfg(unix)]
    pub(super) fn inherit_shared_cache_locks(&self, command: &mut cargo_util::ProcessBuilder) {
        for lock in self.locks.read().unwrap().values() {
            if let UnitLock::Reserved { file, .. } = lock {
                command.inherit_file(Arc::clone(file));
            }
        }
    }

    /// Takes a shared lock on a given [`Unit`]
    /// This prevents other Cargo instances from compiling (writing) to
    /// this build unit.
    ///
    /// This function returns a [`LockKey`] which can be used to upgrade/unlock a dynamic
    /// lock. Reserved shared-cache locks keep their preparation-time mode throughout.
    #[instrument(skip_all, fields(key))]
    pub fn lock_shared(
        &self,
        build_runner: &BuildRunner<'_, '_>,
        unit: &Unit,
    ) -> CargoResult<LockKey> {
        let key = self.key_for_unit(build_runner, unit);
        tracing::Span::current().record("key", key.0.to_str());

        let mut locks = self.locks.write().unwrap();
        if let Some(lock) = locks.get_mut(&key) {
            if let UnitLock::Dynamic(lock) = lock {
                flock::lock_shared(lock.file())?;
            }
        } else {
            #[cfg(unix)]
            if locks.is_empty() {
                Self::reserve_descriptor_budget(build_runner.bcx.unit_graph.len());
            }

            let fs = Filesystem::new(key.0.clone());
            let lock_msg = format!(
                "{} ({})",
                unit.pkg.name(),
                build_runner.files().unit_hash(unit)
            );
            let lock = fs.open_ro_shared_create(&key.0, build_runner.bcx.gctx, &lock_msg)?;
            locks.insert(key.clone(), UnitLock::Dynamic(lock));
        }

        Ok(key)
    }

    #[cfg(unix)]
    fn reserve_descriptor_budget(unit_count: usize) {
        Self::reserve_descriptor_budget_with(
            unit_count,
            || {
                let mut limit = std::mem::MaybeUninit::<libc::rlimit>::uninit();
                // SAFETY: `limit` points to writable storage for one `rlimit`, and
                // `RLIMIT_NOFILE` does not retain the pointer beyond this call.
                if unsafe { libc::getrlimit(libc::RLIMIT_NOFILE, limit.as_mut_ptr()) } != 0 {
                    return Err(std::io::Error::last_os_error());
                }

                // SAFETY: A successful `getrlimit` call initialized every field of `limit`.
                Ok(unsafe { limit.assume_init() })
            },
            |limit| {
                // SAFETY: `limit` is initialized and remains valid for the call; the
                // requested soft limit cannot exceed the unchanged process hard limit.
                if unsafe { libc::setrlimit(libc::RLIMIT_NOFILE, limit) } != 0 {
                    return Err(std::io::Error::last_os_error());
                }

                Ok(())
            },
        );
    }

    #[cfg(unix)]
    fn reserve_descriptor_budget_with(
        unit_count: usize,
        get_limit: impl FnOnce() -> std::io::Result<libc::rlimit>,
        set_limit: impl FnOnce(&libc::rlimit) -> std::io::Result<()>,
    ) {
        // Fine-grained locking retains one descriptor for each compilation unit. Leave room
        // for Cargo's other files, compiler pipes, and the jobserver in the same process.
        const RESERVED_DESCRIPTORS: libc::rlim_t = 128;

        let mut limit = match get_limit() {
            Ok(limit) => limit,
            Err(error) => {
                tracing::warn!(
                    "could not inspect the file-descriptor limit for {unit_count} fine-grained build locks; continuing with the existing limit: {error}"
                );
                return;
            }
        };
        let required = libc::rlim_t::try_from(unit_count)
            .unwrap_or(libc::RLIM_INFINITY)
            .saturating_add(RESERVED_DESCRIPTORS);

        if limit.rlim_cur >= required {
            return;
        }

        let previous = limit.rlim_cur;
        limit.rlim_cur = required.min(limit.rlim_max);
        if limit.rlim_cur == previous {
            tracing::warn!(
                "file-descriptor hard limit {} is below the requested budget {required} for {unit_count} fine-grained build locks; continuing with the existing limit",
                limit.rlim_max
            );
            return;
        }

        if let Err(error) = set_limit(&limit) {
            tracing::warn!(
                "could not raise the file-descriptor soft limit from {previous} to {} (hard limit {}) for {unit_count} fine-grained build locks; continuing with the existing limit: {error}",
                limit.rlim_cur,
                limit.rlim_max
            );
            return;
        }

        if limit.rlim_cur < required {
            tracing::warn!(
                "raised the file-descriptor soft limit from {previous} to its hard limit {}, below the requested budget {required} for {unit_count} fine-grained build locks",
                limit.rlim_cur
            );
        } else {
            tracing::debug!(
                "raised file-descriptor soft limit from {previous} to {} for {unit_count} fine-grained build locks",
                limit.rlim_cur
            );
        }
    }

    #[instrument(skip(self))]
    pub fn lock(&self, key: &LockKey) -> CargoResult<()> {
        let locks = self.locks.read().unwrap();
        if let Some(lock) = locks.get(&key) {
            match lock {
                UnitLock::Dynamic(lock) => flock::lock_exclusive(lock.file())?,
                UnitLock::Reserved {
                    exclusive: true, ..
                } => {}
                UnitLock::Reserved {
                    exclusive: false, ..
                } => {
                    bail!("shared registry writer was not reserved before preparation: {key}");
                }
            }
        } else {
            bail!("lock was not found in lock manager: {key}");
        }

        Ok(())
    }

    /// Downgrades a dynamic lock; reserved shared-cache leases retain their original mode.
    #[instrument(skip(self))]
    pub fn downgrade_to_shared(&self, key: &LockKey) -> CargoResult<()> {
        let locks = self.locks.read().unwrap();
        let Some(lock) = locks.get(key) else {
            bail!("lock was not found in lock manager: {key}");
        };
        if let UnitLock::Dynamic(lock) = lock {
            flock::lock_shared(lock.file())?;
        }
        Ok(())
    }

    #[instrument(skip(self))]
    pub fn unlock(&self, key: &LockKey) -> CargoResult<()> {
        let locks = self.locks.read().unwrap();
        if let Some(UnitLock::Dynamic(lock)) = locks.get(key) {
            flock::unlock(lock.file())?;
        };

        Ok(())
    }
}

#[derive(Debug, Clone, Hash, Eq, PartialEq, Ord, PartialOrd)]
pub struct LockKey(PathBuf);

impl LockKey {
    fn from_unit(build_runner: &BuildRunner<'_, '_>, unit: &Unit) -> Self {
        Self(build_runner.files().build_unit_lock(unit))
    }
}

impl Display for LockKey {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0.display())
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::LockManager;
    use std::cell::Cell;

    #[test]
    fn descriptor_budget_ignores_denied_or_unsupported_inspection() {
        for error in [libc::EPERM, libc::ENOSYS] {
            let setter_called = Cell::new(false);
            LockManager::reserve_descriptor_budget_with(
                512,
                || Err(std::io::Error::from_raw_os_error(error)),
                |_| {
                    setter_called.set(true);
                    Ok(())
                },
            );

            assert!(!setter_called.get());
        }
    }

    #[test]
    fn descriptor_budget_ignores_denied_or_unsupported_updates() {
        for error in [libc::EPERM, libc::ENOSYS] {
            let attempted = Cell::new(None);
            LockManager::reserve_descriptor_budget_with(
                72,
                || {
                    Ok(libc::rlimit {
                        rlim_cur: 64,
                        rlim_max: 512,
                    })
                },
                |limit| {
                    attempted.set(Some((limit.rlim_cur, limit.rlim_max)));
                    Err(std::io::Error::from_raw_os_error(error))
                },
            );

            assert_eq!(attempted.get(), Some((200, 512)));
        }
    }

    #[test]
    fn descriptor_budget_never_exceeds_the_process_hard_limit() {
        let attempted = Cell::new(None);
        LockManager::reserve_descriptor_budget_with(
            512,
            || {
                Ok(libc::rlimit {
                    rlim_cur: 64,
                    rlim_max: 96,
                })
            },
            |limit| {
                attempted.set(Some((limit.rlim_cur, limit.rlim_max)));
                Ok(())
            },
        );

        assert_eq!(attempted.get(), Some((96, 96)));
    }

    #[test]
    fn descriptor_budget_skips_sufficient_or_already_capped_limits() {
        for (soft, hard, units) in [(256, 512, 64), (64, 64, 512)] {
            let setter_called = Cell::new(false);
            LockManager::reserve_descriptor_budget_with(
                units,
                || {
                    Ok(libc::rlimit {
                        rlim_cur: soft,
                        rlim_max: hard,
                    })
                },
                |_| {
                    setter_called.set(true);
                    Ok(())
                },
            );

            assert!(!setter_called.get());
        }
    }
}
