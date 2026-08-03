//! Parallel parsing for previously downloaded registry manifests.
//!
//! Workers only parse and deserialize owned manifest contents. Cargo's global
//! context, manifest normalization, package validation, and diagnostics all
//! remain on the calling thread.

use std::path::Path;
use std::sync::Arc;
use std::sync::LazyLock;
use std::sync::Mutex;
use std::sync::mpsc;

use futures::channel::oneshot;

use crate::core::EitherManifest;
use crate::core::SourceId;
use crate::util::CargoResult;
use crate::util::GlobalContext;

use super::PreparedManifest;

/// Coordinates one cached registry package's parsing and completion order.
pub(crate) struct RegistryManifestParse {
    pool: &'static ParserPool,
    previous: Option<oneshot::Receiver<()>>,
    complete: oneshot::Sender<()>,
}

impl RegistryManifestParse {
    /// Reserves a package's turn before unpacking or any other fallible work.
    ///
    /// If worker threads cannot be started, the caller uses its existing
    /// synchronous manifest-loading path.
    pub(crate) fn reserve() -> Option<Self> {
        // Share one bounded worker pool across all registry sources for the
        // lifetime of the Cargo process.
        static POOL: LazyLock<std::io::Result<ParserPool>> = LazyLock::new(ParserPool::new);

        let pool = POOL.as_ref().ok()?;
        let (complete, receiver) = oneshot::channel();
        let previous = pool
            .previous
            .lock()
            .expect("manifest parser completion queue was poisoned")
            .replace(receiver);

        Some(Self {
            pool,
            previous,
            complete,
        })
    }

    /// Parses a registry manifest while preserving source-order diagnostics.
    pub(crate) async fn read(
        &mut self,
        path: &Path,
        source_id: SourceId,
        gctx: &GlobalContext,
    ) -> CargoResult<EitherManifest> {
        debug_assert!(source_id.is_remote_registry());

        let contents = super::read_toml_string(path, false, gctx)?;
        let prepared = match self.pool.submit(contents) {
            Ok(result) => result
                .await
                .map_err(|_| anyhow::anyhow!("manifest parser worker exited unexpectedly"))?,
            Err(contents) => super::prepare_manifest(contents, false),
        };

        self.wait_for_previous().await;
        super::finish_manifest(path, source_id, gctx, prepared)
    }

    /// Releases this package's turn after all source validation has finished.
    ///
    /// Waiting here also preserves the first error when unpacking or reading
    /// a later package fails before its manifest reaches a worker.
    pub(crate) async fn finish(mut self) {
        self.wait_for_previous().await;
        let _ = self.complete.send(());
    }

    async fn wait_for_previous(&mut self) {
        if let Some(previous) = self.previous.take() {
            let _ = previous.await;
        }
    }
}

struct ParserPool {
    tasks: mpsc::Sender<ParseTask>,
    previous: Mutex<Option<oneshot::Receiver<()>>>,
}

impl ParserPool {
    fn new() -> std::io::Result<Self> {
        let workers = std::thread::available_parallelism()
            .map_or(1, std::num::NonZeroUsize::get)
            .min(4);
        let (tasks, receiver) = mpsc::channel::<ParseTask>();
        let receiver = Arc::new(Mutex::new(receiver));

        for index in 0..workers {
            let receiver = Arc::clone(&receiver);
            std::thread::Builder::new()
                .name(format!("cargo-manifest-parser-{index}"))
                .spawn(move || {
                    loop {
                        let task = match receiver
                            .lock()
                            .expect("manifest parser task queue was poisoned")
                            .recv()
                        {
                            Ok(task) => task,
                            Err(_) => return,
                        };

                        let _ = task
                            .result
                            .send(super::prepare_manifest(task.contents, false));
                    }
                })?;
        }

        Ok(Self {
            tasks,
            previous: Mutex::new(None),
        })
    }

    fn submit(&self, contents: String) -> Result<oneshot::Receiver<PreparedManifest>, String> {
        let (sender, receiver) = oneshot::channel();
        self.tasks
            .send(ParseTask {
                contents,
                result: sender,
            })
            .map_err(|task| task.0.contents)?;

        Ok(receiver)
    }
}

struct ParseTask {
    contents: String,
    result: oneshot::Sender<PreparedManifest>,
}
