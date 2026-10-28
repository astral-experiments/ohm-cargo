use annotate_snippets::{AnnotationKind, Level, Patch, Renderer, Snippet};
fn main() {
    let source = "line 1\nline 2\nline 3\nline 4\nline 5\nline 6\nline 7\nline 8\nline 9\nline 10\nline 11\nline 12\nline 13\n";
    let input = &[
        Level::ERROR
            .primary_title("main diagnostic message")
            .id("test-diagnostic")
            .element(
                Snippet::source(source)
                    .path("example.py")
                    .annotation(AnnotationKind::Primary.span(7..13)),
            ),
        Level::HELP.secondary_title("Replace three lines").element(
            Snippet::source(source)
                .patch(Patch::new(7..7, "fixed "))
                .patch(Patch::new(42..42, "fixed "))
                .patch(Patch::new(87..87, "fixed ")),
        ),
    ];
print!("{}", Renderer::plain().render(input));
}
