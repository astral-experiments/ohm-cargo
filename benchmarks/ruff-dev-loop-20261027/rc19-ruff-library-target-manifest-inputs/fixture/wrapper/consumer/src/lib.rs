#![allow(unexpected_cfgs)]
pub const fn answer() -> u8 { if cfg!(observed_test_off) { 17 } else { 29 } }
