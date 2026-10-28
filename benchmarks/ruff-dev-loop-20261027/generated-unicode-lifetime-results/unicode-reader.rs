use unicode_names2::{character, name};
fn main() {
    for (ch, official) in [('A',"LATIN CAPITAL LETTER A"), ('\u{2603}',"SNOWMAN"), ('\u{1f980}',"CRAB")] {
        assert_eq!(name(ch).unwrap().to_string(), official);
        assert_eq!(character(official), Some(ch));
        println!("{ch:?} {official}");
    }
    assert_eq!(character("LINE FEED"), Some('\n'));
    assert_eq!(character("THIS IS NOT AN OFFICIAL UNICODE NAME"), None);
    println!("LF alias and absent spelling checked");
}
