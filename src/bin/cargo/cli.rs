use crate::util::data_structures::HashMap;
use anyhow::{Context as _, anyhow};
use cargo::core::{CliUnstable, features};
use cargo::util::context::TermConfig;
use cargo::{CargoResult, drop_print, drop_println};
use cargo_util_terminal::report::Level;
use clap::builder::UnknownArgumentValueParser;
use itertools::Itertools;
use std::ffi::OsStr;
use std::ffi::OsString;
use std::fmt::Write;

use super::commands;
use super::list_commands;
use super::third_party_subcommands;
use super::user_defined_aliases;
use crate::command_prelude::*;
use crate::util::is_rustup;
use cargo::util::style;
use cargo_util_terminal::ColorChoice;

#[tracing::instrument(skip_all)]
pub fn main(gctx: &mut GlobalContext) -> CliResult {
    // CAUTION: Be careful with using `config` until it is configured below.
    // In general, try to avoid loading config values unless necessary (like
    // the [alias] table).

    #[cfg(unix)]
    if let Some(client) = commands::session::Client::parse(std::env::args_os().skip(1)) {
        // Keep the config reads performed by CLI construction and execution,
        // including warnings emitted before resolving aliases.
        let _ = gctx.get::<TermConfig>("term");
        if matches!(super::aliased_command(gctx, "session"), Ok(Some(_))) {
            warn_shadowed_builtin_alias(gctx, "session")?;
        }
        gctx.configure(0, false, None, false, false, false, &None, &[], &[])?;
        return client.exec(gctx);
    }

    let args = cli(gctx).try_get_matches()?;

    // Update the process-level notion of cwd
    if let Some(new_cwd) = args.get_one::<std::path::PathBuf>("directory") {
        // This is a temporary hack.
        // This cannot access `GlobalContext`, so this is a bit messy.
        // This does not properly parse `-Z` flags that appear after the subcommand.
        // The error message is not as helpful as the standard one.
        let nightly_features_allowed = matches!(&*features::channel(), "nightly" | "dev");
        if !nightly_features_allowed
            || (nightly_features_allowed
                && !args
                    .get_many("unstable-features")
                    .map(|mut z| z.any(|value: &String| value == "unstable-options"))
                    .unwrap_or(false))
        {
            return Err(anyhow::format_err!(
                "the `-C` flag is unstable, \
                 pass `-Z unstable-options` on the nightly channel to enable it"
            )
            .into());
        }
        std::env::set_current_dir(&new_cwd).context("could not change to requested directory")?;
        gctx.reload_cwd()?;
    }

    let (expanded_args, global_args) = expand_aliases(gctx, args, vec![])?;

    #[cfg(unix)]
    if let Some(raw) = &global_args.session_client_args {
        // Alias expansion preserves the terminal client's raw argv. Parsing it
        // with the direct client keeps `--` and request globals on the same side
        // of the protocol boundary as a literal invocation.
        global_args.validate_session_client()?;
        let client = commands::session::Client::parse(raw.iter().cloned())
            .expect("alias expansion retained a recognized session client");
        gctx.configure(0, false, None, false, false, false, &None, &[], &[])?;
        return client.exec(gctx);
    }

    let is_verbose = expanded_args.verbose() > 0;

    if expanded_args
        .get_one::<String>("unstable-features")
        .map(String::as_str)
        == Some("help")
    {
        // Don't let config errors get in the way of parsing arguments
        let _ = configure_gctx(gctx, &expanded_args, None, global_args, None);
        print_zhelp(gctx);
    } else if expanded_args.flag("version") {
        // Don't let config errors get in the way of parsing arguments
        let _ = configure_gctx(gctx, &expanded_args, None, global_args, None);
        let version = get_version_string(is_verbose);
        drop_print!(gctx, "{}", version);
    } else if let Some(code) = expanded_args.get_one::<String>("explain") {
        // Don't let config errors get in the way of parsing arguments
        let _ = configure_gctx(gctx, &expanded_args, None, global_args, None);
        let mut process = gctx.load_global_rustc(None)?.process();
        process.arg("--explain").arg(code).exec()?;
    } else if expanded_args.flag("list") {
        // Don't let config errors get in the way of parsing arguments
        let _ = configure_gctx(gctx, &expanded_args, None, global_args, None);
        print_list(gctx, is_verbose);
    } else {
        let (cmd, subcommand_args) = match expanded_args.subcommand() {
            Some((cmd, args)) => (cmd, args),
            _ => {
                // No subcommand provided.
                cli(gctx).print_help()?;
                return Ok(());
            }
        };
        let exec = Exec::infer(cmd)?;
        let session_client = is_session_client(&expanded_args);
        if session_client {
            // Globals collected before expanding an alias are no longer in
            // the expanded clap matches, but cannot override a live session.
            global_args.validate_session_client()?;
            commands::session::validate_client_options(&expanded_args, subcommand_args)?;
        }
        // A session must reconstruct fresh contexts after planning
        // invalidation, including global options collected while expanding
        // aliases. Nested serve arguments also own check's --target-dir.
        let session = (cmd == "session")
            .then(|| subcommand_args.subcommand())
            .flatten()
            .filter(|(command, _)| *command == "serve")
            .map(|(_, args)| (args, global_args.clone()));
        configure_gctx(
            gctx,
            &expanded_args,
            Some(session.as_ref().map_or(subcommand_args, |(args, _)| *args)),
            global_args,
            Some(&exec),
        )?;
        // Socket-only session clients do not access repositories. Avoid loading
        // libgit2 and its TLS certificate store on every check.
        if !session_client {
            super::init_git();
        }

        if let Some((args, globals)) = session {
            commands::session::serve(gctx, args, |fresh, requested| {
                let inherited = globals
                    .clone()
                    .merge_for_session(GlobalArgs::new(&expanded_args));
                configure_gctx(
                    fresh,
                    requested,
                    requested.subcommand().map(|(_, args)| args),
                    inherited,
                    Some(&exec),
                )
            })?;
        } else {
            exec.exec(gctx, subcommand_args)?;
        }
    }
    Ok(())
}

fn is_session_client(args: &ArgMatches) -> bool {
    matches!(
        args.subcommand(),
        Some(("session", args))
            if matches!(args.subcommand_name(), Some("check" | "build" | "clippy" | "test" | "bench" | "status" | "stop"))
    )
}

fn print_zhelp(gctx: &GlobalContext) {
    let header = style::HEADER;
    let literal = style::LITERAL;
    let placeholder = style::PLACEHOLDER;

    let options = CliUnstable::help();
    let max_length = options
        .iter()
        .filter(|(_, help)| help.is_some())
        .map(|(option_name, _)| option_name.len())
        .max()
        .unwrap_or(0);
    let z_flags = options
        .iter()
        .filter(|(_, help)| help.is_some())
        .map(|(opt, help)| {
            let opt = opt.replace("_", "-");
            let help = help.unwrap();
            format!("    {literal}-Z {opt:<max_length$}{literal:#}  {help}")
        })
        .join("\n");
    drop_println!(
        gctx,
        "\
{header}Available unstable (nightly-only) flags:{header:#}

{z_flags}

Run with `{literal}cargo -Z{literal:#} {placeholder}[FLAG] [COMMAND]{placeholder:#}`",
    );
    if !gctx.nightly_features_allowed {
        drop_println!(
            gctx,
            "\nUnstable flags are only available on the nightly channel \
                 of Cargo, but this is the `{}` channel.\n\
                 {}",
            features::channel(),
            features::SEE_CHANNELS
        );
    }
    drop_println!(
        gctx,
        "\nSee https://doc.rust-lang.org/nightly/cargo/reference/unstable.html \
             for more information about these flags."
    );
}

fn print_list(gctx: &GlobalContext, is_verbose: bool) {
    // Maps from commonly known external commands (not builtin to cargo)
    // to their description, for the help page. Reserved for external
    // subcommands that are core within the rust ecosystem (esp ones that
    // might become internal in the future).
    let known_external_command_descriptions = HashMap::from_iter([
        (
            "clippy",
            "Checks a package to catch common mistakes and improve your Rust code.",
        ),
        (
            "fmt",
            "Formats all bin and lib files of the current crate using rustfmt.",
        ),
    ]);
    drop_println!(
        gctx,
        color_print::cstr!("<bright-green,bold>Installed Commands:</>")
    );
    for (name, command) in list_commands(gctx) {
        let known_external_desc = known_external_command_descriptions.get(name.as_str());
        let literal = style::LITERAL;
        match command {
            CommandInfo::BuiltIn { about } => {
                assert!(
                    known_external_desc.is_none(),
                    "known_external_commands shouldn't contain builtin `{name}`",
                );
                let summary = about.unwrap_or_default();
                let summary = summary.lines().next().unwrap_or(&summary); // display only the first line
                drop_println!(gctx, "    {literal}{name:<20}{literal:#} {summary}");
            }
            CommandInfo::External { path } => {
                if let Some(desc) = known_external_desc {
                    drop_println!(gctx, "    {literal}{name:<20}{literal:#} {desc}");
                } else if is_verbose {
                    drop_println!(
                        gctx,
                        "    {literal}{name:<20}{literal:#} {}",
                        path.display()
                    );
                } else {
                    drop_println!(gctx, "    {literal}{name}{literal:#}");
                }
            }
            CommandInfo::Alias { target } => {
                drop_println!(
                    gctx,
                    "    {literal}{name:<20}{literal:#} alias: {}",
                    target.iter().join(" ")
                );
            }
        }
    }
}

pub fn get_version_string(is_verbose: bool) -> String {
    let version = cargo::version();
    let mut version_string = format!("cargo {}\n", version);
    if is_verbose {
        version_string.push_str(&format!("release: {}\n", version.version));
        if let Some(ref ci) = version.commit_info {
            version_string.push_str(&format!("commit-hash: {}\n", ci.commit_hash));
            version_string.push_str(&format!("commit-date: {}\n", ci.commit_date));
        }
        writeln!(version_string, "host: {}", env!("RUST_HOST_TARGET")).unwrap();
        add_libgit2(&mut version_string);
        add_curl(&mut version_string);
        add_ssl(&mut version_string);
        writeln!(version_string, "os: {}", os_info::get()).unwrap();
    }
    version_string
}

fn add_libgit2(version_string: &mut String) {
    let git2_v = git2::Version::get();
    let lib_v = git2_v.libgit2_version();
    let vendored = if git2_v.vendored() {
        format!("vendored")
    } else {
        format!("system")
    };
    writeln!(
        version_string,
        "libgit2: {}.{}.{} (sys:{} {})",
        lib_v.0,
        lib_v.1,
        lib_v.2,
        git2_v.crate_version(),
        vendored
    )
    .unwrap();
}

fn add_curl(version_string: &mut String) {
    let curl_v = curl::Version::get();
    let vendored = if curl_v.vendored() {
        format!("vendored")
    } else {
        format!("system")
    };
    writeln!(
        version_string,
        "libcurl: {} (sys:{} {} ssl:{})",
        curl_v.version(),
        curl_sys::rust_crate_version(),
        vendored,
        curl_v.ssl_version().unwrap_or("none")
    )
    .unwrap();
}

fn add_ssl(version_string: &mut String) {
    #[cfg(feature = "openssl")]
    {
        writeln!(version_string, "ssl: {}", openssl::version::version()).unwrap();
    }
    #[cfg(not(feature = "openssl"))]
    {
        let _ = version_string; // Silence unused warning.
    }
}

/// Expands aliases recursively to collect all the command line arguments.
///
/// [`GlobalArgs`] need to be extracted before expanding aliases because the
/// clap code for extracting a subcommand discards global options
/// (appearing before the subcommand).
#[tracing::instrument(skip_all)]
fn expand_aliases(
    gctx: &mut GlobalContext,
    args: ArgMatches,
    mut already_expanded: Vec<String>,
) -> Result<(ArgMatches, GlobalArgs), CliError> {
    if let Some((cmd, sub_args)) = args.subcommand() {
        let exec = commands::builtin_exec(cmd);
        let aliased_cmd = super::aliased_command(gctx, cmd);

        match (exec, aliased_cmd) {
            (Some(_), Ok(Some(_))) => {
                // User alias conflicts with a built-in subcommand
                warn_shadowed_builtin_alias(gctx, cmd)?;
            }
            (Some(_), Ok(None) | Err(_)) => {
                // Here we ignore errors from aliasing as we already favor built-in command,
                // and alias doesn't involve in this context.

                if let Some(values) = sub_args.get_many::<OsString>("") {
                    // Command is built-in and is not conflicting with alias, but contains ignored values.
                    return Err(anyhow::format_err!(
                        "\
trailing arguments after built-in command `{}` are unsupported: `{}`

To pass the arguments to the subcommand, remove `--`",
                        cmd,
                        values.map(|s| s.to_string_lossy()).join(" "),
                    )
                    .into());
                }
            }
            (None, Ok(None)) => {}
            (None, Ok(Some(alias))) => {
                // Check if a user-defined alias is shadowing an external subcommand
                // (binary of the form `cargo-<subcommand>`)
                // Currently this is only a warning, but after a transition period this will become
                // a hard error.
                if super::builtin_aliases_execs(cmd).is_none() {
                    if let Some(path) = super::find_external_subcommand(gctx, cmd) {
                        gctx.shell().print_report(
                            &[
                                Level::WARNING.secondary_title(format!(
                                    "user-defined alias `{}` is shadowing an external subcommand found at `{}`",
                                    cmd,
                                    path.display()
                                )).element(
                                    Level::NOTE.message(
                                        "this was previously accepted but will become a hard error in the future; \
                                        see <https://github.com/rust-lang/cargo/issues/10049>"
                                    )
                                )
                            ],
                            false,
                        )?;
                    }
                }
                if commands::run::is_manifest_command(cmd) {
                    if gctx.cli_unstable().script {
                        return Ok((args, GlobalArgs::default()));
                    } else {
                        gctx.shell().print_report(
                            &[
                                Level::WARNING.secondary_title(
                                    format!("user-defined alias `{cmd}` has the appearance of a manifest-command")
                                ).element(
                                    Level::NOTE.message(
                                        "this was previously accepted but will be phased out when `-Zscript` is stabilized; \
                                        see <https://github.com/rust-lang/cargo/issues/12207>"
                                    )
                                )
                            ],
                            false
                        )?;
                    }
                }

                let mut alias = alias
                    .into_iter()
                    .map(|s| OsString::from(s))
                    .collect::<Vec<_>>();
                alias.extend(
                    sub_args
                        .get_many::<OsString>("")
                        .unwrap_or_default()
                        .cloned(),
                );
                // new_args strips out everything before the subcommand, so
                // capture those global options now.
                // Note that an alias to an external command will not receive
                // these arguments. That may be confusing, but such is life.
                let mut global_args = GlobalArgs::new(sub_args);
                #[cfg(unix)]
                let session_client_args =
                    commands::session::Client::parse(alias.iter().cloned()).map(|_| alias.clone());
                #[cfg(not(unix))]
                let session_client_args: Option<Vec<OsString>> = None;
                // Parse only the dispatch prefix of a recognized client. Clap
                // must not consume its Cargo globals or its leading `--` before
                // the same client parser used for literal invocations sees them.
                let new_args = cli(gctx).no_binary_name(true).try_get_matches_from(
                    session_client_args
                        .as_ref()
                        .map_or(alias.as_slice(), |raw| &raw[..2]),
                )?;

                let Some(new_cmd) = new_args.subcommand_name() else {
                    return Err(anyhow!(
                        "subcommand is required, add a subcommand to the command alias `alias.{cmd}`"
                    )
                        .into());
                };

                already_expanded.push(cmd.to_string());
                if already_expanded.contains(&new_cmd.to_string()) {
                    // Crash if the aliases are corecursive / unresolvable
                    return Err(anyhow!(
                        "alias {} has unresolvable recursive definition: {} -> {}",
                        already_expanded[0],
                        already_expanded.join(" -> "),
                        new_cmd,
                    )
                    .into());
                }

                let (expanded_args, nested_globals) =
                    expand_aliases(gctx, new_args, already_expanded)?;
                // Validate at every layer: intermediate aliases can carry
                // global flags which ordinary alias expansion does not retain.
                if is_session_client(&expanded_args) {
                    global_args.validate_session_client()?;
                    commands::session::validate_client_options(
                        &args,
                        expanded_args.subcommand_matches("session").unwrap(),
                    )?;
                    global_args.session_client_args =
                        session_client_args.or(nested_globals.session_client_args.clone());
                }
                let global_args = match expanded_args.subcommand() {
                    Some(("session", args)) if args.subcommand_name() == Some("serve") => {
                        global_args.merge_for_session(nested_globals)
                    }
                    _ => global_args,
                };
                return Ok((expanded_args, global_args));
            }
            (None, Err(e)) => return Err(e.into()),
        }
    };

    Ok((args, GlobalArgs::default()))
}

fn warn_shadowed_builtin_alias(gctx: &GlobalContext, cmd: &str) -> CargoResult<()> {
    gctx.shell().warn(format!(
        "user-defined alias `{cmd}` is ignored, because it is shadowed by a built-in command",
    ))
}

#[tracing::instrument(skip_all)]
fn configure_gctx(
    gctx: &mut GlobalContext,
    args: &ArgMatches,
    subcommand_args: Option<&ArgMatches>,
    global_args: GlobalArgs,
    exec: Option<&Exec>,
) -> CliResult {
    let arg_target_dir = &subcommand_args.and_then(|a| a.value_of_path("target-dir", gctx));
    let mut verbose = global_args.verbose + args.verbose();
    // quiet is unusual because it is redefined in some subcommands in order
    // to provide custom help text.
    let mut quiet = args.flag("quiet")
        || subcommand_args.map(|a| a.flag("quiet")).unwrap_or_default()
        || global_args.quiet;
    if matches!(exec, Some(Exec::Manifest(_))) && !quiet {
        // Verbosity is shifted quieter for `Exec::Manifest` as it is can be used as if you ran
        // `cargo install` and we especially shouldn't pollute programmatic output.
        //
        // For now, interactive output has the same default output as `cargo run` but that is
        // subject to change.
        if let Some(lower) = verbose.checked_sub(1) {
            verbose = lower;
        } else if !gctx.shell().is_err_tty() {
            // Don't pollute potentially-scripted output
            quiet = true;
        }
    }
    let global_color = global_args.color; // Extract so it can take reference.
    let color = args
        .get_one::<String>("color")
        .map(String::as_str)
        .or_else(|| global_color.as_deref());
    let frozen = args.flag("frozen") || global_args.frozen;
    let locked = args.flag("locked") || global_args.locked;
    let offline = args.flag("offline") || global_args.offline;
    let mut unstable_flags = global_args.unstable_flags;
    if let Some(values) = args.get_many::<String>("unstable-features") {
        unstable_flags.extend(values.cloned());
    }
    let mut config_args = global_args.config_args;
    if let Some(values) = args.get_many::<String>("config") {
        config_args.extend(values.cloned());
    }
    gctx.configure(
        verbose,
        quiet,
        color,
        frozen,
        locked,
        offline,
        arg_target_dir,
        &unstable_flags,
        &config_args,
    )?;
    Ok(())
}

enum Exec {
    Builtin(commands::Exec),
    Manifest(String),
    External(String),
}

impl Exec {
    /// Precedence isn't the most obvious from this function because
    /// - Some is determined by `expand_aliases`
    /// - Some is enforced by `avoid_ambiguity_between_builtins_and_manifest_commands`
    ///
    /// In actuality, it is:
    /// 1. built-ins xor manifest-command
    /// 2. aliases
    /// 3. external subcommands
    fn infer(cmd: &str) -> CargoResult<Self> {
        if let Some(exec) = commands::builtin_exec(cmd) {
            Ok(Self::Builtin(exec))
        } else if commands::run::is_manifest_command(cmd) {
            Ok(Self::Manifest(cmd.to_owned()))
        } else {
            Ok(Self::External(cmd.to_owned()))
        }
    }

    #[tracing::instrument(skip_all)]
    fn exec(self, gctx: &mut GlobalContext, subcommand_args: &ArgMatches) -> CliResult {
        match self {
            Self::Builtin(exec) => exec(gctx, subcommand_args),
            Self::Manifest(cmd) => {
                let ext_path = super::find_external_subcommand(gctx, &cmd);
                if !gctx.cli_unstable().script && ext_path.is_some() {
                    gctx.shell().print_report(
                        &[
                            Level::WARNING.secondary_title(
                                format!("external subcommand `{cmd}` has the appearance of a manifest-command")
                            ).element(
                                Level::NOTE.message(
                                    "this was previously accepted but will be phased out when `-Zscript` is stabilized; \
                                    see <https://github.com/rust-lang/cargo/issues/12207>"
                                )
                            )
                        ],
                        false
                    )?;

                    Self::External(cmd).exec(gctx, subcommand_args)
                } else {
                    let ext_args: Vec<OsString> = subcommand_args
                        .get_many::<OsString>("")
                        .unwrap_or_default()
                        .cloned()
                        .collect();
                    commands::run::exec_manifest_command(gctx, &cmd, &ext_args)
                }
            }
            Self::External(cmd) => {
                let mut ext_args = vec![OsStr::new(&cmd)];
                ext_args.extend(
                    subcommand_args
                        .get_many::<OsString>("")
                        .unwrap_or_default()
                        .map(OsString::as_os_str),
                );
                super::execute_external_subcommand(gctx, &cmd, &ext_args)
            }
        }
    }
}

#[derive(Clone, Default, Eq, PartialEq)]
struct GlobalArgs {
    verbose: u32,
    quiet: bool,
    color: Option<String>,
    frozen: bool,
    locked: bool,
    offline: bool,
    unstable_flags: Vec<String>,
    config_args: Vec<String>,
    /// Exact argv of a recognized terminal client after alias expansion.
    session_client_args: Option<Vec<OsString>>,
}

impl GlobalArgs {
    /// Preserve each alias layer for a session's fixed configuration. Arguments
    /// in the final clap matches still take precedence in `configure_gctx`.
    fn merge_for_session(mut self, inner: Self) -> Self {
        self.verbose += inner.verbose;
        self.quiet |= inner.quiet;
        self.frozen |= inner.frozen;
        self.locked |= inner.locked;
        self.offline |= inner.offline;
        if inner.color.is_some() {
            self.color = inner.color;
        }
        self.unstable_flags.extend(inner.unstable_flags);
        self.config_args.extend(inner.config_args);
        self
    }

    fn validate_session_client(&self) -> CliResult {
        if self.verbose != 0
            || self.quiet
            || self.color.is_some()
            || self.frozen
            || self.locked
            || self.offline
            || !self.unstable_flags.is_empty()
            || !self.config_args.is_empty()
        {
            return Err(anyhow!(
                "session clients accept only --socket and --json; pass global options to `cargo session serve`"
            ).into());
        }
        Ok(())
    }

    fn new(args: &ArgMatches) -> GlobalArgs {
        GlobalArgs {
            verbose: args.verbose(),
            quiet: args.flag("quiet"),
            color: args.get_one::<String>("color").cloned(),
            frozen: args.flag("frozen"),
            locked: args.flag("locked"),
            offline: args.flag("offline"),
            unstable_flags: args
                .get_many::<String>("unstable-features")
                .unwrap_or_default()
                .cloned()
                .collect(),
            config_args: args
                .get_many::<String>("config")
                .unwrap_or_default()
                .cloned()
                .collect(),
            session_client_args: None,
        }
    }
}

#[tracing::instrument(skip_all)]
pub fn cli(gctx: &GlobalContext) -> Command {
    // Don't let config errors get in the way of parsing arguments
    let term = gctx.get::<TermConfig>("term").unwrap_or_default();
    let color = term
        .color
        .and_then(|c| c.parse().ok())
        .unwrap_or(ColorChoice::CargoAuto);
    let color = match color {
        ColorChoice::Always => clap::ColorChoice::Always,
        ColorChoice::Never => clap::ColorChoice::Never,
        ColorChoice::CargoAuto => clap::ColorChoice::Auto,
    };

    let usage = if is_rustup() {
        color_print::cstr!(
            "<bright-cyan,bold>cargo</> <cyan>[+toolchain] [OPTIONS] [COMMAND]</>\n       <bright-cyan,bold>cargo</> <cyan>[+toolchain] [OPTIONS]</> <bright-cyan,bold>-Zscript</> <cyan><<MANIFEST_RS>> [ARGS]...</>"
        )
    } else {
        color_print::cstr!(
            "<bright-cyan,bold>cargo</> <cyan>[OPTIONS] [COMMAND]</>\n       <bright-cyan,bold>cargo</> <cyan>[OPTIONS]</> <bright-cyan,bold>-Zscript</> <cyan><<MANIFEST_RS>> [ARGS]...</>"
        )
    };

    let styles = {
        clap::builder::styling::Styles::styled()
            .header(style::HEADER)
            .usage(style::USAGE)
            .literal(style::LITERAL)
            .placeholder(style::PLACEHOLDER)
            .error(style::ERROR)
            .valid(style::VALID)
            .invalid(style::INVALID)
    };

    Command::new("cargo")
        // Subcommands all count their args' display order independently (from 0),
        // which makes their args interspersed with global args. This puts global args last.
        //
        // We also want these to come before auto-generated `--help`
        .next_display_order(800)
        .allow_external_subcommands(true)
        .color(color)
        .styles(styles)
        // Provide a custom help subcommand for calling into man pages
        .disable_help_subcommand(true)
        .override_usage(usage)
        .help_template(color_print::cstr!(
            "\
Rust's package manager

<bright-green,bold>Usage:</> {usage}

<bright-green,bold>Options:</>
{options}

<bright-green,bold>Commands:</>
    <bright-cyan,bold>build</>, <bright-cyan,bold>b</>    Compile the current package
    <bright-cyan,bold>check</>, <bright-cyan,bold>c</>    Analyze the current package and report errors, but don't build object files
    <bright-cyan,bold>clean</>       Remove the target directory
    <bright-cyan,bold>doc</>, <bright-cyan,bold>d</>      Build this package's and its dependencies' documentation
    <bright-cyan,bold>new</>         Create a new cargo package
    <bright-cyan,bold>init</>        Create a new cargo package in an existing directory
    <bright-cyan,bold>add</>         Add dependencies to a manifest file
    <bright-cyan,bold>remove</>      Remove dependencies from a manifest file
    <bright-cyan,bold>run</>, <bright-cyan,bold>r</>      Run a binary or example of the local package
    <bright-cyan,bold>test</>, <bright-cyan,bold>t</>     Run the tests
    <bright-cyan,bold>bench</>       Run the benchmarks
    <bright-cyan,bold>update</>      Update dependencies listed in Cargo.lock
    <bright-cyan,bold>search</>      Search registry for crates
    <bright-cyan,bold>publish</>     Package and upload this package to the registry
    <bright-cyan,bold>install</>     Install a Rust binary
    <bright-cyan,bold>uninstall</>   Uninstall a Rust binary
    <cyan>...</>         See all commands with <bright-cyan,bold>--list</>

See '<bright-cyan,bold>cargo help</> <cyan><<command>></>' for more information on a specific command.\n",
        ))
        .arg(flag("version", "Print version info and exit").short('V'))
        .arg(flag("list", "List installed commands"))
        .arg(
            opt(
                "explain",
                "Provide a detailed explanation of a rustc error message",
            )
            .value_name("CODE"),
        )
        .arg(
            opt(
                "verbose",
                "Use verbose output (-vv very verbose/build.rs output)",
            )
            .short('v')
            .action(ArgAction::Count)
            .global(true),
        )
        .arg(flag("quiet", "Do not print cargo log messages").short('q').global(true))
        .arg(
            opt("color", "Coloring")
                .value_name("WHEN")
                .global(true)
                .value_parser(["auto", "always", "never"])
                .ignore_case(true),
        )
        .arg(
            Arg::new("directory")
                .help("Change to DIRECTORY before doing anything (nightly-only)")
                .short('C')
                .value_name("DIRECTORY")
                .value_hint(clap::ValueHint::DirPath)
                .value_parser(clap::builder::ValueParser::path_buf()),
        )
        .arg(
            flag("locked", "Assert that `Cargo.lock` will remain unchanged")
                .help_heading(heading::MANIFEST_OPTIONS)
                .global(true),
        )
        .arg(
            flag("offline", "Run without accessing the network")
                .help_heading(heading::MANIFEST_OPTIONS)
                .global(true),
        )
        .arg(
            flag("frozen", "Equivalent to specifying both --locked and --offline")
                .help_heading(heading::MANIFEST_OPTIONS)
                .global(true),
        )
        // Better suggestion for the unsupported short config flag.
        .arg( Arg::new("unsupported-short-config-flag")
            .help("")
            .short('c')
            .value_parser(UnknownArgumentValueParser::suggest_arg("--config"))
            .action(ArgAction::SetTrue)
            .global(true)
            .hide(true))
        .arg(multi_opt("config", "KEY=VALUE|PATH", "Override a configuration value").add(clap_complete::engine::ArgValueCompleter::new(
                    clap_complete::engine::PathCompleter::any()
                        .filter(|path| path.is_file() && path.extension() == Some(OsStr::new("toml"))),
                )).global(true))
        // Better suggestion for the unsupported lowercase unstable feature flag.
        .arg( Arg::new("unsupported-lowercase-unstable-feature-flag")
            .help("")
            .short('z')
            .value_parser(UnknownArgumentValueParser::suggest_arg("-Z"))
            .action(ArgAction::SetTrue)
            .global(true)
            .hide(true))
        .arg(Arg::new("unstable-features")
            .help("Unstable (nightly-only) flags to Cargo, see 'cargo -Z help' for details")
            .short('Z')
            .value_name("FLAG")
            .action(ArgAction::Append)
            .global(true)
        .add(clap_complete::ArgValueCandidates::new(|| {
            let flags = CliUnstable::help();
            flags.into_iter().map(|flag| {
                clap_complete::CompletionCandidate::new(flag.0.replace("_", "-")).help(flag.1.map(|help| {
                    help.into()
                }))
            }).collect()
        })))
        .add(clap_complete::engine::SubcommandCandidates::new(move || {
            let mut candidates = get_toolchains_from_rustup()
                .into_iter()
                .map(|t| clap_complete::CompletionCandidate::new(t))
                .collect::<Vec<_>>();
            if let Ok(gctx) = new_gctx_for_completions() {
                candidates.extend(get_command_candidates(&gctx));
            }
            candidates
        }))
        .subcommands(commands::builtin())
}

fn get_toolchains_from_rustup() -> Vec<String> {
    let output = std::process::Command::new("rustup")
        .arg("toolchain")
        .arg("list")
        .arg("-q")
        .output()
        .unwrap();

    if !output.status.success() {
        return vec![];
    }

    let stdout = String::from_utf8(output.stdout).unwrap();

    stdout.lines().map(|line| format!("+{}", line)).collect()
}

fn get_command_candidates(gctx: &GlobalContext) -> Vec<clap_complete::CompletionCandidate> {
    let mut commands = user_defined_aliases(gctx);
    commands.extend(third_party_subcommands(gctx));
    commands
        .iter()
        .map(|(name, cmd_info)| {
            let help_text = match cmd_info {
                CommandInfo::Alias { target } => {
                    let cmd_str = target
                        .iter()
                        .map(String::as_str)
                        .collect::<Vec<_>>()
                        .join(" ");
                    format!("alias for {}", cmd_str)
                }
                CommandInfo::BuiltIn { .. } => {
                    unreachable!("BuiltIn command shouldn't appear in alias map")
                }
                CommandInfo::External { path } => {
                    format!("from {}", path.display())
                }
            };
            clap_complete::CompletionCandidate::new(name.clone()).help(Some(help_text.into()))
        })
        .collect()
}

#[test]
fn verify_cli() {
    let gctx = GlobalContext::default().unwrap();
    cli(&gctx).debug_assert();
}

#[test]
fn avoid_ambiguity_between_builtins_and_manifest_commands() {
    for cmd in commands::builtin() {
        let name = cmd.get_name();
        assert!(
            !commands::run::is_manifest_command(&name),
            "built-in command {name} is ambiguous with manifest-commands"
        )
    }
}

#[cfg(all(test, unix))]
mod session_client_alias_tests {
    use super::*;
    use cargo_util_terminal::Shell;
    use std::os::unix::ffi::OsStringExt;

    fn raw(args: &[&str]) -> Vec<OsString> {
        args.iter().map(OsString::from).collect()
    }

    fn context(root: &std::path::Path) -> GlobalContext {
        let mut gctx = GlobalContext::new(Shell::new(), root.to_owned(), root.join("home"));
        gctx.set_search_stop_path(root.to_owned());
        gctx.set_env(
            [
                ("CARGO_ALIAS_SCHECK", "session check"),
                ("CARGO_ALIAS_STEST", "session test"),
                ("CARGO_ALIAS_SCLIPPY", "session clippy"),
                ("CARGO_ALIAS_NESTED", "sclippy"),
                ("CARGO_ALIAS_OUTER", "--offline nested"),
            ]
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value.to_owned()))
            .collect(),
        );
        gctx
    }

    fn expanded(
        gctx: &mut GlobalContext,
        args: Vec<OsString>,
    ) -> Result<commands::session::Client, CliError> {
        let matches =
            cli(gctx).try_get_matches_from([OsString::from("cargo")].into_iter().chain(args))?;
        let (_, globals) = expand_aliases(gctx, matches, Vec::new())?;
        globals.validate_session_client()?;
        Ok(
            commands::session::Client::parse(globals.session_client_args.unwrap().into_iter())
                .unwrap(),
        )
    }

    #[test]
    fn terminal_aliases_preserve_client_and_cargo_argument_boundaries() {
        let dir = tempfile::tempdir().unwrap();
        let mut gctx = context(&dir.path().canonicalize().unwrap());
        for (alias, command, arguments) in [
            ("sclippy", "clippy", raw(&["--", "-Dwarnings"])),
            ("nested", "clippy", raw(&["--", "-Dwarnings"])),
            ("stest", "test", raw(&["--", "--ignored"])),
            ("stest", "test", raw(&["module", "--", "--exact"])),
            (
                "scheck",
                "check",
                raw(&["-p", "app", "--json", "--socket", "session.sock"]),
            ),
            (
                "scheck",
                "check",
                raw(&["--offline", "--config", "build.jobs=2"]),
            ),
            (
                "stest",
                "test",
                vec![
                    OsString::from("--socket"),
                    OsString::from_vec(b"session-\xff.sock".to_vec()),
                    OsString::from("--"),
                    OsString::from_vec(b"filter-\xfe".to_vec()),
                ],
            ),
        ] {
            let literal = commands::session::Client::parse(
                raw(&["session", command])
                    .into_iter()
                    .chain(arguments.clone()),
            )
            .unwrap();
            let aliased = expanded(
                &mut gctx,
                [OsString::from(alias)]
                    .into_iter()
                    .chain(arguments)
                    .collect(),
            )
            .unwrap();
            assert_eq!(aliased, literal, "alias {alias}");
        }
    }

    #[test]
    fn outer_alias_and_root_options_cannot_configure_the_client() {
        let dir = tempfile::tempdir().unwrap();
        let mut gctx = context(&dir.path().canonicalize().unwrap());
        for arguments in [
            raw(&["--offline", "scheck"]),
            raw(&["--color", "never", "nested"]),
            raw(&["-C", ".", "scheck"]),
            raw(&["outer"]),
        ] {
            let error = expanded(&mut gctx, arguments).err().unwrap();
            assert!(
                error
                    .error
                    .unwrap()
                    .to_string()
                    .contains("session clients accept only"),
            );
        }
    }
}
