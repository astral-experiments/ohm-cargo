//! Deferred configuration of libgit2 for the Cargo executable.

use std::sync::{Once, OnceLock};

static INITIALIZER: GitInitializer = GitInitializer::new();

/// Register the executable's libgit2 configuration before running a command.
///
/// The callback runs once, before Cargo first opens or creates a Git repository
/// or starts workers that may read its certificate environment.
/// Cargo's library users do not register it, so they retain libgit2's default
/// owner validation. The callback must not recursively call Cargo's Git helpers.
///
/// # Panics
///
/// Panics if an initializer has already been registered.
#[doc(hidden)]
pub fn register_git_initializer(callback: fn()) {
    INITIALIZER.register(callback);
}

/// Apply the executable's policy before accessing a libgit2 repository.
pub(crate) fn ensure_git_initialized() {
    INITIALIZER.ensure_initialized();
}

struct GitInitializer {
    callback: OnceLock<fn()>,
    initialized: Once,
}

impl GitInitializer {
    const fn new() -> Self {
        Self {
            callback: OnceLock::new(),
            initialized: Once::new(),
        }
    }

    fn register(&self, callback: fn()) {
        self.callback
            .set(callback)
            .expect("the Git initializer must only be registered once");
    }

    fn ensure_initialized(&self) {
        if let Some(callback) = self.callback.get() {
            self.initialized.call_once(*callback);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::GitInitializer;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn registration_is_lazy_and_concurrent_access_initializes_once() {
        static CALLS: AtomicUsize = AtomicUsize::new(0);
        fn initialize() {
            CALLS.fetch_add(1, Ordering::SeqCst);
        }

        let initializer = GitInitializer::new();
        // Library access without an executable callback must not consume the Once.
        initializer.ensure_initialized();
        initializer.register(initialize);
        assert_eq!(CALLS.load(Ordering::SeqCst), 0);

        std::thread::scope(|scope| {
            for _ in 0..8 {
                scope.spawn(|| initializer.ensure_initialized());
            }
        });
        initializer.ensure_initialized();
        assert_eq!(CALLS.load(Ordering::SeqCst), 1);
    }

    #[test]
    #[should_panic(expected = "the Git initializer must only be registered once")]
    fn duplicate_registration_is_rejected() {
        let initializer = GitInitializer::new();
        initializer.register(|| {});
        initializer.register(|| {});
    }
}
