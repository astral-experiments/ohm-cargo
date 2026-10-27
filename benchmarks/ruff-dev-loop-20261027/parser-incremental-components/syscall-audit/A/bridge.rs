pub fn observed() -> String { match ruff_python_parser::parse_module("t'first' b'second'\n") { Err(err) => err.to_string(), Ok(_) => panic!("invalid parser fixture") } }
