//! Last-use and compiler provenance for one shared build root.
//!
//! This database uses Cargo's SQLite migration helpers, but not its package-cache
//! database or locks: shared build roots have their own consumer leases.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::ensure;
use cargo_util::paths;
use rusqlite::config::DbConfig;
use rusqlite::{Connection, OpenFlags, OptionalExtension as _, params};

use super::{Anchor, ContextRecord, FileIdentity, absent, installed_ohm_version, metadata_dir};
use crate::CargoResult;
use crate::util::sqlite::{self, basic_migration};
use crate::workspace::global_cache_tracker::UPDATE_RESOLUTION;

pub(super) const DATABASE: &str = "cache.sqlite";
const SCHEMA_VERSION: u32 = 2;

/// Nanoseconds preserve exact GC cutoffs; recorded use is rounded upward.
pub(super) type Timestamp = i64;

pub(super) fn timestamp(time: SystemTime) -> CargoResult<Timestamp> {
    Ok(time.duration_since(UNIX_EPOCH)?.as_nanos().try_into()?)
}

pub(crate) struct Tracker {
    pub(super) conn: Connection,
}

pub(super) struct Context {
    pub record: ContextRecord,
    pub last_used: Option<Timestamp>,
    pub all_used: Option<Timestamp>,
}

impl Tracker {
    /// Opens or initializes metadata while the caller holds a consumer lease.
    pub(super) fn open(root: &Path) -> CargoResult<Self> {
        metadata_dir(root, true)?;
        let mut conn = Self::connect(root, OpenFlags::default())?;
        let version: u32 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
        ensure!(
            version <= SCHEMA_VERSION,
            "unsupported build-cache database version {version}"
        );
        let mode: String =
            conn.pragma_update_and_check(None, "journal_mode", "WAL", |row| row.get(0))?;
        ensure!(
            mode == "wal",
            "shared build-cache database requires WAL support"
        );
        conn.pragma_update(None, "synchronous", "NORMAL")?;
        if version < SCHEMA_VERSION {
            sqlite::migrate(
                &mut conn,
                &[
                    basic_migration(
                        "CREATE TABLE contexts (
                                context TEXT PRIMARY KEY NOT NULL,
                                record BLOB NOT NULL,
                                last_used INTEGER,
                                all_used INTEGER
                            )",
                    ),
                    basic_migration(
                            "CREATE TABLE dependencies (
                                context TEXT NOT NULL REFERENCES contexts(context) ON DELETE CASCADE,
                                entry BLOB NOT NULL,
                                last_used INTEGER NOT NULL,
                                PRIMARY KEY (context, entry)
                            ) WITHOUT ROWID",
                        ),
                ],
            )?;
        }
        Ok(Self { conn })
    }

    /// GC never creates or migrates a database, including during a dry run.
    pub(super) fn existing(root: &Path, dry_run: bool) -> CargoResult<Option<Self>> {
        let directory = root.join(super::DIRECTORY);
        if absent(&directory) {
            return Ok(None);
        }
        metadata_dir(root, false)?;
        if absent(&directory.join(DATABASE)) {
            ensure!(
                ["-journal", "-wal", "-shm"]
                    .iter()
                    .all(|suffix| absent(&directory.join(format!("{DATABASE}{suffix}")))),
                "build-cache database is missing but its journal remains"
            );
            return Ok(None);
        }
        let flags = if dry_run {
            OpenFlags::SQLITE_OPEN_READ_ONLY
        } else {
            OpenFlags::SQLITE_OPEN_READ_WRITE
        };
        let conn = Self::connect(root, flags)?;
        let version: u32 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
        ensure!(
            version == SCHEMA_VERSION,
            "unsupported build-cache database version {version}"
        );
        Ok(Some(Self { conn }))
    }

    fn connect(root: &Path, flags: OpenFlags) -> CargoResult<Connection> {
        let directory = metadata_dir(root, false)?;
        let before = fs::symlink_metadata(&directory)?;
        for name in [
            DATABASE.to_owned(),
            format!("{DATABASE}-journal"),
            format!("{DATABASE}-wal"),
            format!("{DATABASE}-shm"),
        ] {
            let path = directory.join(name);
            match fs::symlink_metadata(&path) {
                Ok(metadata) => ensure!(
                    metadata.is_file(),
                    "build-cache database is not a regular file"
                ),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(error.into()),
            }
        }
        let conn = Connection::open_with_flags(
            directory.join(DATABASE),
            flags | OpenFlags::SQLITE_OPEN_NOFOLLOW | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )?;
        let after = fs::symlink_metadata(&directory)?;
        ensure!(
            after.is_dir(),
            "build-cache metadata changed while opening it"
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt as _;
            ensure!(
                (before.dev(), before.ino()) == (after.dev(), after.ino()),
                "build-cache metadata changed while opening it"
            );
        }
        #[cfg(not(unix))]
        let _ = before;
        conn.pragma_update(None, "foreign_keys", true)?;
        // These are reconstructible cache timestamps, like the unsynced mtime
        // markers they replace. WAL + NORMAL keeps transactions atomic without
        // syncing every warm build. Keep SQLite's automatic size-based checkpoints,
        // but do not force another checkpoint whenever a Cargo process exits.
        conn.set_db_config(DbConfig::SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, true)?;
        if !flags.contains(OpenFlags::SQLITE_OPEN_READ_ONLY) {
            let mode: String = conn.pragma_query_value(None, "journal_mode", |row| row.get(0))?;
            if mode == "wal" {
                conn.pragma_update(None, "synchronous", "NORMAL")?;
            }
        }
        Ok(conn)
    }

    /// Immutable provenance is written only when the compiler context is first seen.
    pub(super) fn record_context(
        &self,
        context: &str,
        compiler: FileIdentity,
        driver: FileIdentity,
    ) -> CargoResult<()> {
        if self.conn.query_row(
            "SELECT EXISTS(SELECT 1 FROM contexts WHERE context = ?1)",
            [context],
            |row| row.get::<_, bool>(0),
        )? {
            return Ok(());
        }
        self.insert_context(&ContextRecord {
            version: if super::scoped_context_name(context) {
                2
            } else {
                1
            },
            context: context.to_owned(),
            ohm_version: installed_ohm_version(&compiler, &driver),
            compiler_anchor: Anchor::for_path(&compiler.path)?,
            driver_anchor: Anchor::for_path(&driver.path)?,
            compiler,
            driver,
        })
    }

    pub(super) fn insert_context(&self, record: &ContextRecord) -> CargoResult<()> {
        self.conn.execute(
            "INSERT OR IGNORE INTO contexts (context, record) VALUES (?1, ?2)",
            params![record.context, serde_json::to_vec(record)?],
        )?;
        Ok(())
    }

    pub(super) fn contexts(&self) -> CargoResult<Vec<String>> {
        Ok(self
            .conn
            .prepare_cached("SELECT context FROM contexts")?
            .query_map([], |row| row.get(0))?
            .collect::<rusqlite::Result<_>>()?)
    }

    pub(super) fn context(&self, context: &str) -> CargoResult<Option<Context>> {
        let row: Option<(Vec<u8>, Option<Timestamp>, Option<Timestamp>)> = self
            .conn
            .prepare_cached("SELECT record, last_used, all_used FROM contexts WHERE context = ?1")?
            .query_row([context], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))
            .optional()?;
        row.map(|(record, last_used, all_used)| {
            Ok(Context {
                record: serde_json::from_slice(&record)?,
                last_used,
                all_used,
            })
        })
        .transpose()
    }

    /// Records selected units, including fresh hits, at Cargo's update resolution.
    /// Rounding upward guarantees a full hour of inactivity despite skipped writes.
    /// A snapshot import has no resolved graph and protects the whole context.
    pub(super) fn touch(
        &mut self,
        context: &str,
        entries: Option<&[PathBuf]>,
        now: SystemTime,
    ) -> CargoResult<Timestamp> {
        let resolution = Duration::from_secs(UPDATE_RESOLUTION).as_nanos();
        let now: Timestamp = (now
            .duration_since(UNIX_EPOCH)?
            .as_nanos()
            .div_ceil(resolution)
            * resolution)
            .try_into()?;
        // Keep warm builds read-only. End this snapshot before writing so another
        // consumer's commit cannot make a read-to-write upgrade fail as busy.
        let (update_context, pending) = {
            let tx = self.conn.transaction()?;
            let (last_used, all_used): (Option<Timestamp>, Option<Timestamp>) = tx
                .prepare_cached("SELECT last_used, all_used FROM contexts WHERE context = ?1")?
                .query_row([context], |row| Ok((row.get(0)?, row.get(1)?)))?;
            let update_context = last_used.is_none_or(|used| used < now)
                || (entries.is_none() && all_used.is_none_or(|used| used < now));
            let mut pending = Vec::new();
            if let Some(entries) = entries {
                let mut statement = tx.prepare_cached(
                    "SELECT last_used FROM dependencies WHERE context = ?1 AND entry = ?2",
                )?;
                for entry in entries {
                    let used: Option<Timestamp> = statement
                        .query_row(params![context, paths::path2bytes(entry)?], |row| {
                            row.get(0)
                        })
                        .optional()?;
                    if used.is_none_or(|used| used < now) {
                        pending.push(entry);
                    }
                }
            }
            (update_context, pending)
        };
        if !update_context && pending.is_empty() {
            return Ok(now);
        }
        // Short Cargo invocations rebuild the WAL index on open. Keep small batches'
        // logs small, but let larger batches amortize checkpoint synchronization.
        let checkpoint_pages = entries.map_or(128, |entries| {
            entries.len().saturating_mul(2).clamp(128, 1_000)
        });
        self.conn
            .pragma_update(None, "wal_autocheckpoint", checkpoint_pages as u32)?;
        let tx = self.conn.transaction()?;
        if update_context {
            let changed = tx.prepare_cached("UPDATE contexts SET last_used = max(coalesce(last_used, ?2), ?2), all_used = CASE WHEN ?3 THEN max(coalesce(all_used, ?2), ?2) ELSE all_used END WHERE context = ?1")?
                .execute(params![context, now, entries.is_none()])?;
            ensure!(changed == 1, "missing build-context provenance");
        }
        if !pending.is_empty() {
            let mut statement = tx.prepare_cached("INSERT INTO dependencies (context, entry, last_used) VALUES (?1, ?2, ?3) ON CONFLICT (context, entry) DO UPDATE SET last_used = max(last_used, excluded.last_used)")?;
            for entry in pending {
                statement.execute(params![context, paths::path2bytes(entry)?, now])?;
            }
        }
        tx.commit()?;
        Ok(now)
    }

    /// The primary key narrows the scan to this context. A timestamp index would
    /// add work to every cache hit just to accelerate infrequent manual GC.
    pub(super) fn idle_dependencies(
        &self,
        context: &str,
        cutoff: Timestamp,
    ) -> CargoResult<Vec<PathBuf>> {
        self.conn
            .prepare_cached(
                "SELECT entry FROM dependencies WHERE context = ?1 AND last_used <= ?2",
            )?
            .query_map(params![context, cutoff], |row| row.get::<_, Vec<u8>>(0))?
            .map(|row| paths::bytes2path(&row?))
            .collect()
    }

    /// Rechecks each candidate after acquiring the consumer lock, without relying
    /// on a stale scan or holding a read transaction during filesystem inspection.
    pub(super) fn dependency_expired(
        &self,
        context: &str,
        entry: &Path,
        cutoff: Timestamp,
    ) -> CargoResult<bool> {
        Ok(self.conn.prepare_cached("SELECT EXISTS(SELECT 1 FROM dependencies JOIN contexts USING (context) WHERE context = ?1 AND entry = ?2 AND dependencies.last_used <= ?3 AND (all_used IS NULL OR all_used <= ?3))")?
            .query_row(params![context, paths::path2bytes(entry)?, cutoff], |row| row.get(0))?)
    }

    pub(super) fn forget_context(&self, context: &str) -> CargoResult<()> {
        self.conn
            .execute("DELETE FROM contexts WHERE context = ?1", [context])?;
        Ok(())
    }

    pub(super) fn forget_dependency(&self, context: &str, entry: &Path) -> CargoResult<()> {
        self.conn.execute(
            "DELETE FROM dependencies WHERE context = ?1 AND entry = ?2",
            params![context, paths::path2bytes(entry)?],
        )?;
        Ok(())
    }
}
