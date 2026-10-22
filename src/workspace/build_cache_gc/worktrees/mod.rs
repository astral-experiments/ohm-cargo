//! Reclaims obsolete compiler intermediates in registered private workspace targets.

#[cfg(any(target_os = "linux", target_os = "macos"))]
pub(crate) mod activity;
pub(crate) mod provenance;
#[cfg(any(target_os = "linux", target_os = "macos"))]
pub(crate) mod registry;

#[cfg(any(target_os = "linux", target_os = "macos"))]
mod collector;
#[cfg(any(target_os = "linux", target_os = "macos"))]
mod idle;
#[cfg(any(target_os = "linux", target_os = "macos"))]
mod mounts;
#[cfg(any(target_os = "linux", target_os = "macos"))]
pub(crate) use collector::collect;
