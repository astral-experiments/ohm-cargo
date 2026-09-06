//! Parse each request with Cargo's command schemas and the server's explicit defaults.

use std::ffi::{OsStr, OsString};

use clap::parser::ValueSource;

use crate::command_prelude::*;

use super::protocol::Operation;

pub(super) struct ParsedCommand {
    pub root: ArgMatches,
    pub clippy_args: Option<String>,
    pub clippy_fix: bool,
}

/// Apply server defaults only after validating the request's own arguments.
///
/// Rebuilding argv from the option definitions leaves clap responsible for
/// aliases, duplicate options, conflicts, and help. Cargo globals are supplied
/// separately by the server's configuration factory.
pub(super) fn parse(
    gctx: &GlobalContext,
    defaults: &ArgMatches,
    operation: Operation,
    raw: &[OsString],
) -> Result<ParsedCommand, CliError> {
    let (command, arguments, clippy_args, clippy_fix) = match operation {
        Operation::Check => ("check", raw.to_vec(), None, false),
        Operation::Build => ("build", raw.to_vec(), None, false),
        Operation::Test => ("test", raw.to_vec(), None, false),
        Operation::Bench => ("bench", raw.to_vec(), None, false),
        Operation::Clippy => lower_clippy(raw)?,
        Operation::Status | Operation::Stop => {
            return Err(
                anyhow::anyhow!("session administration requests have no build arguments").into(),
            );
        }
    };
    let parser = crate::cli::cli(gctx);
    let request = parser.clone().try_get_matches_from(
        [OsStr::new("cargo"), OsStr::new(command)]
            .into_iter()
            .chain(arguments.iter().map(OsString::as_os_str)),
    )?;
    let requested = request.subcommand_matches(command).unwrap();
    let schema = parser.find_subcommand(command).unwrap();
    let check = crate::commands::check::cli();
    let selects_packages = has_explicit_group(requested, schema, heading::PACKAGE_SELECTION);
    let selects_targets = has_explicit_group(requested, schema, heading::TARGET_SELECTION);
    let selects_profile = explicit(requested, "profile") || explicit(requested, "release");
    let mut inherited = Vec::new();
    for option in check.get_arguments() {
        let id = option.get_id().as_str();
        let Some(selected_option) = schema.get_arguments().find(|arg| arg.get_id() == id) else {
            continue;
        };
        if !explicit(defaults, id)
            || explicit(requested, id)
            || parser.get_arguments().any(|arg| arg.get_id() == id)
            // Some commands keep a hidden suggestion for an unsupported option,
            // such as `cargo test --keep-going`. Those aren't applicable defaults.
            || (selected_option.is_hide_set() && !option.is_hide_set())
        {
            continue;
        }
        match option.get_help_heading() {
            Some(heading::PACKAGE_SELECTION) if selects_packages => continue,
            Some(heading::TARGET_SELECTION) if selects_packages || selects_targets => continue,
            _ => {}
        }
        if selects_profile && matches!(id, "profile" | "release") {
            continue;
        }
        append_default(&mut inherited, option, defaults);
    }
    let root = if inherited.is_empty() {
        request
    } else {
        parser.try_get_matches_from(
            [OsString::from("cargo"), OsString::from(command)]
                .into_iter()
                .chain(inherited)
                .chain(arguments),
        )?
    };
    Ok(ParsedCommand {
        root,
        clippy_args,
        clippy_fix,
    })
}

fn explicit(args: &ArgMatches, id: &str) -> bool {
    args.ids().any(|candidate| candidate == id)
        && args.value_source(id) == Some(ValueSource::CommandLine)
}

fn has_explicit_group(args: &ArgMatches, command: &Command, heading: &str) -> bool {
    command
        .get_arguments()
        .any(|arg| arg.get_help_heading() == Some(heading) && explicit(args, arg.get_id().as_str()))
}

fn append_default(arguments: &mut Vec<OsString>, option: &Arg, defaults: &ArgMatches) {
    let id = option.get_id().as_str();
    let flag = match (option.get_long(), option.get_short()) {
        (Some(long), _) => OsString::from(format!("--{long}")),
        (None, Some(short)) => OsString::from(format!("-{short}")),
        (None, None) => return,
    };
    match option.get_action() {
        ArgAction::Set | ArgAction::Append => {
            for occurrence in defaults.get_raw_occurrences(id).unwrap_or_default() {
                let mut values = occurrence.peekable();
                if values.peek().is_none() {
                    arguments.push(flag.clone());
                }
                for value in values {
                    // Keep arbitrary OS bytes and option-like values intact.
                    let mut argument = flag.clone();
                    argument.push("=");
                    argument.push(value);
                    arguments.push(argument);
                }
            }
        }
        ArgAction::SetTrue | ArgAction::SetFalse => arguments.push(flag),
        ArgAction::Count => {
            arguments.extend((0..defaults.get_count(id)).map(|_| flag.clone()));
        }
        _ => {}
    }
}

/// Match cargo-clippy's split between Cargo options and driver arguments.
fn lower_clippy(
    raw: &[OsString],
) -> Result<(&'static str, Vec<OsString>, Option<String>, bool), CliError> {
    let mut cargo_args = Vec::new();
    let mut driver_args = Vec::new();
    let mut fix = false;
    let mut arguments = raw.iter();
    for argument in arguments.by_ref() {
        if argument == "--" {
            break;
        }
        if argument == "--fix" {
            fix = true;
        } else if argument == "--no-deps" {
            driver_args.push(argument.as_os_str());
        } else {
            cargo_args.push(argument.clone());
        }
    }
    driver_args.extend(arguments.map(OsString::as_os_str));
    if fix && !driver_args.contains(&OsStr::new("--no-deps")) {
        driver_args.push(OsStr::new("--no-deps"));
    }
    let mut encoded = String::new();
    for argument in driver_args {
        let argument = argument.to_str().ok_or_else(|| {
            clap::Error::raw(
                clap::error::ErrorKind::InvalidUtf8,
                "Clippy driver arguments must be valid UTF-8",
            )
        })?;
        encoded.push_str(argument);
        encoded.push_str("__CLIPPY_HACKERY__");
    }
    Ok((
        if fix { "fix" } else { "check" },
        cargo_args,
        Some(encoded),
        fix,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(raw: &[&str]) -> Vec<OsString> {
        raw.iter().map(OsString::from).collect()
    }

    fn defaults(gctx: &GlobalContext, raw: &[&str]) -> ArgMatches {
        let root = crate::cli::cli(gctx)
            .try_get_matches_from(
                ["cargo", "session", "serve"]
                    .into_iter()
                    .chain(raw.iter().copied()),
            )
            .unwrap();
        root.subcommand_matches("session")
            .unwrap()
            .subcommand_matches("serve")
            .unwrap()
            .clone()
    }

    #[test]
    fn defaults_are_explicit_and_request_options_take_precedence() {
        let gctx = GlobalContext::default().unwrap();
        let defaults = defaults(
            &gctx,
            &[
                "-p",
                "app",
                "--lib",
                "--features",
                "defaulted",
                "-j",
                "4",
                "--offline",
                "--socket",
                "session.sock",
            ],
        );
        let parsed = parse(
            &gctx,
            &defaults,
            Operation::Build,
            &args(&["-j", "2", "-F", "requested"]),
        )
        .unwrap();
        let build = parsed.root.subcommand_matches("build").unwrap();
        assert_eq!(build.get_one::<String>("package").unwrap(), "app");
        assert!(build.get_flag("lib"));
        assert_eq!(build.get_one::<String>("jobs").unwrap(), "2");
        assert_eq!(
            build
                .get_many::<String>("features")
                .unwrap()
                .collect::<Vec<_>>(),
            [&"requested".to_owned()]
        );
        assert!(!parsed.root.get_flag("offline"));
        assert!(parsed.clippy_args.is_none());
        assert!(!parsed.clippy_fix);
    }

    #[test]
    fn package_and_target_selection_replace_the_relevant_defaults() {
        let gctx = GlobalContext::default().unwrap();
        let defaults = defaults(&gctx, &["-p", "app", "--lib"]);
        let parsed = parse(
            &gctx,
            &defaults,
            Operation::Test,
            &args(&["--test", "integration"]),
        )
        .unwrap();
        let test = parsed.root.subcommand_matches("test").unwrap();
        assert_eq!(test.get_one::<String>("package").unwrap(), "app");
        assert_eq!(test.get_one::<String>("test").unwrap(), "integration");
        assert!(!test.get_flag("lib"));

        let parsed = parse(&gctx, &defaults, Operation::Build, &args(&["-p", "other"])).unwrap();
        let build = parsed.root.subcommand_matches("build").unwrap();
        assert_eq!(build.get_one::<String>("package").unwrap(), "other");
        assert!(!build.get_flag("lib"));

        let parsed = parse(&gctx, &defaults, Operation::Test, &args(&["--doc"])).unwrap();
        let test = parsed.root.subcommand_matches("test").unwrap();
        assert!(test.get_flag("doc"));
        assert!(!test.get_flag("lib"));
    }

    #[test]
    fn profiles_override_release_and_command_specific_defaults_stay_applicable() {
        let gctx = GlobalContext::default().unwrap();
        let defaults = defaults(&gctx, &["--release", "--keep-going", "--compile-time-deps"]);
        let parsed = parse(
            &gctx,
            &defaults,
            Operation::Test,
            &args(&["--profile", "dev"]),
        )
        .unwrap();
        let test = parsed.root.subcommand_matches("test").unwrap();
        assert_eq!(test.get_one::<String>("profile").unwrap(), "dev");
        assert!(!test.get_flag("release"));
        assert!(!explicit(test, "keep-going"));

        let parsed = parse(&gctx, &defaults, Operation::Bench, &[]).unwrap();
        assert!(!explicit(
            parsed.root.subcommand_matches("bench").unwrap(),
            "keep-going",
        ));
    }

    #[test]
    fn test_filter_and_runner_arguments_keep_their_boundary() {
        let gctx = GlobalContext::default().unwrap();
        let defaults = defaults(&gctx, &["--lib"]);
        let parsed = parse(
            &gctx,
            &defaults,
            Operation::Test,
            &args(&["module::test", "--", "--exact", "--ignored"]),
        )
        .unwrap();
        let test = parsed.root.subcommand_matches("test").unwrap();
        assert_eq!(test.get_one::<String>("TESTNAME").unwrap(), "module::test");
        assert_eq!(
            test.get_many::<String>("args")
                .unwrap()
                .map(String::as_str)
                .collect::<Vec<_>>(),
            ["--exact", "--ignored"]
        );
        assert!(test.get_flag("lib"));
    }

    #[test]
    fn clippy_fix_and_driver_arguments_follow_cargo_clippy() {
        let gctx = GlobalContext::default().unwrap();
        let defaults = defaults(&gctx, &[]);
        let parsed = parse(
            &gctx,
            &defaults,
            Operation::Clippy,
            &args(&["--fix", "--allow-dirty", "--", "-Dwarnings"]),
        )
        .unwrap();
        assert_eq!(parsed.root.subcommand_name(), Some("fix"));
        assert!(parsed.clippy_fix);
        assert_eq!(
            parsed.clippy_args.as_deref(),
            Some("-Dwarnings__CLIPPY_HACKERY__--no-deps__CLIPPY_HACKERY__")
        );

        let parsed = parse(
            &gctx,
            &defaults,
            Operation::Clippy,
            &args(&["--no-deps", "--", "--fix"]),
        )
        .unwrap();
        assert_eq!(parsed.root.subcommand_name(), Some("check"));
        assert!(!parsed.clippy_fix);
        assert_eq!(
            parsed.clippy_args.as_deref(),
            Some("--no-deps__CLIPPY_HACKERY__--fix__CLIPPY_HACKERY__")
        );
    }

    #[test]
    fn request_duplicates_and_help_keep_clap_exit_behavior() {
        let gctx = GlobalContext::default().unwrap();
        let defaults = defaults(&gctx, &["-j", "4"]);
        let error = parse(
            &gctx,
            &defaults,
            Operation::Build,
            &args(&["-j", "1", "-j", "2"]),
        )
        .err()
        .unwrap();
        assert_eq!(error.exit_code, 1);
        assert_eq!(
            error
                .error
                .unwrap()
                .downcast_ref::<clap::Error>()
                .unwrap()
                .kind(),
            clap::error::ErrorKind::ArgumentConflict
        );
        let help = parse(&gctx, &defaults, Operation::Build, &args(&["--help"]))
            .err()
            .unwrap();
        assert_eq!(help.exit_code, 0);
    }

    #[test]
    fn default_reconstruction_preserves_os_bytes_and_empty_optional_values() {
        use std::os::unix::ffi::OsStringExt;

        let path = Arg::new("path")
            .long("path")
            .value_parser(clap::builder::ValueParser::os_string());
        let empty = Arg::new("optional")
            .long("optional")
            .num_args(0..=1)
            .action(ArgAction::Append);
        let value = OsString::from_vec(b"dir/\xff".to_vec());
        let matches = Command::new("defaults")
            .args([path.clone(), empty.clone()])
            .try_get_matches_from([
                OsString::from("defaults"),
                OsString::from("--path"),
                value.clone(),
                OsString::from("--optional"),
            ])
            .unwrap();
        let mut reconstructed = Vec::new();
        append_default(&mut reconstructed, &path, &matches);
        append_default(&mut reconstructed, &empty, &matches);
        let mut expected = OsString::from("--path=");
        expected.push(value);
        assert_eq!(reconstructed, [expected, OsString::from("--optional")]);
        let error = lower_clippy(&[OsString::from("--"), OsString::from_vec(vec![0xff])])
            .err()
            .unwrap();
        assert_eq!(error.exit_code, 1);
    }
}
