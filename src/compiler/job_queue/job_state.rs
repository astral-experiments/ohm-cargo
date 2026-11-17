//! See [`JobState`].

use std::{
    cell::Cell,
    fmt, fs, marker,
    path::PathBuf,
    sync::{Arc, Mutex},
};

use cargo_util::ProcessBuilder;

use crate::compiler::fingerprint::{BuildState, Fingerprint};
use crate::compiler::future_incompat::FutureBreakageItem;
use crate::compiler::locking::LockKey;
use crate::compiler::timings::SectionTiming;
use crate::context::WarningHandling;
use crate::util::Queue;
use crate::util::interning::InternedString;
use crate::{CargoResult, compiler::locking::LockManager};

use super::{Artifact, DiagDedupe, Job, JobId, Message};

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
pub(crate) struct PublicApiHash {
    pub version: u32,
    pub value: String,
}

impl PublicApiHash {
    pub fn new(version: u32, value: &str) -> Option<Self> {
        (version == 1 && value.len() == 32 && value.bytes().all(|byte| byte.is_ascii_hexdigit()))
            .then(|| Self {
                version,
                value: value.to_ascii_lowercase(),
            })
    }
}

impl fmt::Display for PublicApiHash {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "v{}:{}", self.version, self.value)
    }
}

#[derive(Default)]
enum PublicApiHashState {
    #[default]
    Missing,
    Valid(PublicApiHash),
    Invalid,
}

#[derive(Default)]
enum UnusedExternsState {
    #[default]
    Missing,
    Valid(std::collections::BTreeSet<InternedString>),
    Invalid,
}

struct ConditionalMetadata {
    fingerprint: Arc<Fingerprint>,
    public_api_hash_path: PathBuf,
    previous_public_api_hash: Option<PublicApiHash>,
    ready: Cell<bool>,
    released: Cell<bool>,
}

/// A `JobState` is constructed by `JobQueue::run` and passed to `Job::run`. It includes everything
/// necessary to communicate between the main thread and the execution of the job.
///
/// The job may execute on either a dedicated thread or the main thread. If the job executes on the
/// main thread, the `output` field must be set to prevent a deadlock.
pub struct JobState<'a, 'gctx> {
    /// Channel back to the main thread to coordinate messages and such.
    ///
    /// When the `output` field is `Some`, care must be taken to avoid calling `push_bounded` on
    /// the message queue to prevent a deadlock.
    messages: Arc<Queue<Message>>,

    /// Normally output is sent to the job queue with backpressure. When the job is fresh
    /// however we need to immediately display the output to prevent a deadlock as the
    /// output messages are processed on the same thread as they are sent from. `output`
    /// defines where to output in this case.
    ///
    /// Currently the [`Shell`] inside [`GlobalContext`] is wrapped in a `RefCell` and thus can't
    /// be passed between threads. This means that it isn't possible for multiple output messages
    /// to be interleaved. In the future, it may be wrapped in a `Mutex` instead. In this case
    /// interleaving is still prevented as the lock would be held for the whole printing of an
    /// output message.
    ///
    /// [`Shell`]: cargo_util_terminal::Shell
    /// [`GlobalContext`]: crate::GlobalContext
    output: Option<&'a DiagDedupe<'gctx>>,

    /// The job id that this state is associated with, used when sending
    /// messages back to the main thread.
    id: JobId,

    /// Whether or not we're expected to have a call to `rmeta_produced`. Once
    /// that method is called this is dynamically set to `false` to prevent
    /// sending a double message later on.
    rmeta_required: Cell<bool>,

    /// The public API hash reported by rustc for this unit's metadata artifact.
    ///
    /// This is deliberately kept out of the artifact itself from Cargo's point
    /// of view: rustc is the authority that knows how to compute the hash, and
    /// Cargo only transports and persists the opaque value.
    public_api_hash: Mutex<PublicApiHashState>,

    /// Resolves metadata-only early-cutoff edges once their outcome is known.
    conditional_metadata: Option<ConditionalMetadata>,

    /// Compiler-authoritative direct externs unused by this successful unit.
    unused_externs: Mutex<UnusedExternsState>,

    /// Manages locks for build units when fine grain locking is enabled.
    lock_manager: Arc<LockManager>,

    warning_handling: WarningHandling,

    // Historical versions of Cargo made use of the `'a` argument here, so to
    // leave the door open to future refactorings keep it here.
    _marker: marker::PhantomData<&'a ()>,
}

impl<'a, 'gctx> JobState<'a, 'gctx> {
    pub(super) fn new(
        id: JobId,
        messages: Arc<Queue<Message>>,
        output: Option<&'a DiagDedupe<'gctx>>,
        rmeta_required: bool,
        conditional_metadata: Option<(Arc<Fingerprint>, PathBuf, Option<PublicApiHash>)>,
        lock_manager: Arc<LockManager>,
        warning_handling: WarningHandling,
    ) -> Self {
        Self {
            id,
            messages,
            output,
            rmeta_required: Cell::new(rmeta_required),
            public_api_hash: Mutex::new(PublicApiHashState::Missing),
            conditional_metadata: conditional_metadata.map(
                |(fingerprint, public_api_hash_path, previous_public_api_hash)| {
                    ConditionalMetadata {
                        fingerprint,
                        public_api_hash_path,
                        previous_public_api_hash,
                        ready: Cell::new(false),
                        released: Cell::new(false),
                    }
                },
            ),
            unused_externs: Mutex::new(UnusedExternsState::Missing),
            lock_manager,
            warning_handling,
            _marker: marker::PhantomData,
        }
    }

    pub fn running(&self, cmd: &ProcessBuilder) {
        self.messages.push(Message::Run(self.id, cmd.to_string()));
    }

    pub fn stdout(&self, stdout: String) -> CargoResult<()> {
        if let Some(dedupe) = self.output {
            writeln!(dedupe.gctx.shell().out(), "{}", stdout)?;
        } else {
            self.messages.push_bounded(Message::Stdout(self.id, stdout));
        }
        Ok(())
    }

    pub fn stderr(&self, stderr: String) -> CargoResult<()> {
        if let Some(dedupe) = self.output {
            let mut shell = dedupe.gctx.shell();
            shell.print_ansi_stderr(stderr.as_bytes())?;
            shell.err().write_all(b"\n")?;
        } else {
            self.messages.push_bounded(Message::Stderr(self.id, stderr));
        }
        Ok(())
    }

    /// See [`Message::Diagnostic`] and [`Message::WarningCount`].
    pub fn emit_diag(
        &self,
        level: &str,
        diag: String,
        lint: bool,
        fixable: bool,
    ) -> CargoResult<()> {
        if level == "warning" && lint && self.warning_handling == WarningHandling::Allow {
            tracing::warn!("{diag}");
        } else if let Some(dedupe) = self.output {
            let emitted = dedupe.emit_diag(&diag)?;
            if level == "warning" {
                self.messages.push(Message::WarningCount {
                    id: self.id,
                    lint,
                    emitted,
                    fixable,
                });
            }
        } else {
            self.messages.push_bounded(Message::Diagnostic {
                id: self.id,
                level: level.to_string(),
                diag,
                lint,
                fixable,
            });
        }
        Ok(())
    }

    /// See [`Message::Warning`].
    pub fn warning(&self, warning: String) {
        self.messages.push_bounded(Message::Warning {
            id: self.id,
            warning,
        });
    }

    /// A method used to signal to the coordinator thread that the rmeta file
    /// for an rlib has been produced. This is only called for some rmeta
    /// builds when required, and can be called at any time before a job ends.
    /// This should only be called once because a metadata file can only be
    /// produced once!
    pub fn rmeta_produced(&self) {
        self.rmeta_required.set(false);
        self.messages
            .push(Message::Finish(self.id, Artifact::Metadata, Ok(())));
        if let Some(conditional) = &self.conditional_metadata
            && conditional.ready.get()
            && !conditional.released.replace(true)
        {
            self.messages.push(Message::Finish(
                self.id,
                Artifact::ConditionalMetadata,
                Ok(()),
            ));
        }
    }

    /// Records the public API hash attached to rustc's metadata notification.
    pub(crate) fn public_api_hash_produced(&self, public_api_hash: PublicApiHash) {
        let mut recorded = self.public_api_hash.lock().unwrap();
        match &*recorded {
            PublicApiHashState::Valid(previous) if previous != &public_api_hash => {
                tracing::debug!(
                    "rustc reported conflicting public API hashes; disabling early cutoff"
                );
                *recorded = PublicApiHashState::Invalid;
                if let Some(conditional) = &self.conditional_metadata {
                    conditional.ready.set(false);
                }
            }
            PublicApiHashState::Valid(_) | PublicApiHashState::Invalid => {}
            PublicApiHashState::Missing => {
                if let Some(conditional) = &self.conditional_metadata
                    && conditional
                        .previous_public_api_hash
                        .as_ref()
                        .is_some_and(|previous| previous != &public_api_hash)
                {
                    match fs::remove_file(&conditional.public_api_hash_path) {
                        Ok(()) => {
                            // Invalidate the previously committed hash before a dependent
                            // can observe provisional metadata. Otherwise a later producer
                            // failure followed by a source reversion could reuse artifacts
                            // already committed against the failed producer's metadata.
                            conditional
                                .fingerprint
                                .set_build_state(BuildState::BuiltChanged);
                            conditional.ready.set(true);
                        }
                        Err(error) => {
                            tracing::debug!(
                                "could not invalidate previous public API hash at {}: {}; \
                                 waiting for producer completion",
                                conditional.public_api_hash_path.display(),
                                error
                            );
                        }
                    }
                }
                *recorded = PublicApiHashState::Valid(public_api_hash);
            }
        }
    }

    /// Marks rustc's public API hash notification as malformed.
    pub(crate) fn invalid_public_api_hash(&self) {
        *self.public_api_hash.lock().unwrap() = PublicApiHashState::Invalid;
        if let Some(conditional) = &self.conditional_metadata {
            conditional.ready.set(false);
        }
    }

    /// Returns the public API hash reported by rustc, if one was received.
    pub(crate) fn public_api_hash(&self) -> Option<PublicApiHash> {
        match &*self.public_api_hash.lock().unwrap() {
            PublicApiHashState::Valid(public_api_hash) => Some(public_api_hash.clone()),
            PublicApiHashState::Missing | PublicApiHashState::Invalid => None,
        }
    }

    pub fn lock_exclusive(&self, lock: &LockKey) -> CargoResult<()> {
        self.lock_manager.lock(lock)
    }

    pub fn downgrade_to_shared(&self, lock: &LockKey) -> CargoResult<()> {
        self.lock_manager.downgrade_to_shared(lock)
    }

    pub fn on_section_timing_emitted(&self, section: SectionTiming) {
        self.messages.push(Message::SectionTiming(self.id, section));
    }

    /// Notifies that this unit was skipped via early cutoff.
    pub fn skipped_early_cutoff(&self) {
        self.messages.push(Message::SkippedEarlyCutoff(self.id));
    }

    /// Drives a [`Job`] to finish. This ensures that a [`Message::Finish`] is
    /// sent even if our job panics.
    pub(super) fn run_to_finish(self, job: Job) {
        let mut sender = FinishOnDrop {
            messages: &self.messages,
            id: self.id,
            result: None,
        };
        sender.result = Some(job.run(&self));

        // If the `rmeta_required` wasn't consumed but it was set
        // previously, then we either have:
        //
        // 1. The `job` didn't do anything because it was "fresh".
        // 2. The `job` returned an error and didn't reach the point where
        //    it called `rmeta_produced`.
        // 3. We forgot to call `rmeta_produced` and there's a bug in Cargo.
        //
        // Ruling out the third, the other two are pretty common for 2
        // we'll just naturally abort the compilation operation but for 1
        // we need to make sure that the metadata is flagged as produced so
        // send a synthetic message here.
        if self.rmeta_required.get() && sender.result.as_ref().unwrap().is_ok() {
            self.messages
                .push(Message::Finish(self.id, Artifact::Metadata, Ok(())));
        }

        if sender.result.as_ref().is_some_and(Result::is_ok)
            && let Some(conditional) = &self.conditional_metadata
            && !conditional.released.replace(true)
        {
            self.messages.push(Message::Finish(
                self.id,
                Artifact::ConditionalMetadata,
                Ok(()),
            ));
        }

        // Use a helper struct with a `Drop` implementation to guarantee
        // that a `Finish` message is sent even if our job panics. We
        // shouldn't panic unless there's a bug in Cargo, so we just need
        // to make sure nothing hangs by accident.
        struct FinishOnDrop<'a> {
            messages: &'a Queue<Message>,
            id: JobId,
            result: Option<CargoResult<()>>,
        }

        impl Drop for FinishOnDrop<'_> {
            fn drop(&mut self) {
                let result = self
                    .result
                    .take()
                    .unwrap_or_else(|| Err(anyhow::format_err!("worker panicked")));
                self.messages
                    .push(Message::Finish(self.id, Artifact::All, result));
            }
        }
    }

    pub fn future_incompat_report(&self, report: Vec<FutureBreakageItem>) {
        self.messages
            .push(Message::FutureIncompatReport(self.id, report));
    }

    /// The rustc emitted the list of unused `--extern` args.
    ///
    /// This is useful for checking unused dependencies.
    /// Should only be called once, as the compiler only emits it once per compilation.
    pub fn unused_externs(&self, unused_externs: std::collections::BTreeSet<InternedString>) {
        let mut recorded = self.unused_externs.lock().unwrap();
        let first_report = match &*recorded {
            UnusedExternsState::Missing => {
                *recorded = UnusedExternsState::Valid(unused_externs.clone());
                true
            }
            UnusedExternsState::Valid(previous) if previous != &unused_externs => {
                *recorded = UnusedExternsState::Invalid;
                false
            }
            UnusedExternsState::Valid(_) | UnusedExternsState::Invalid => false,
        };
        drop(recorded);
        if first_report {
            self.messages
                .push(Message::UnusedExterns(self.id, unused_externs));
        }
    }

    /// Rejects compiler usage proof after a malformed unused-extern notification.
    pub(crate) fn invalid_unused_externs(&self) {
        *self.unused_externs.lock().unwrap() = UnusedExternsState::Invalid;
    }

    pub(crate) fn recorded_unused_externs(
        &self,
    ) -> Option<std::collections::BTreeSet<InternedString>> {
        match &*self.unused_externs.lock().unwrap() {
            UnusedExternsState::Valid(unused_externs) => Some(unused_externs.clone()),
            UnusedExternsState::Missing | UnusedExternsState::Invalid => None,
        }
    }
}
