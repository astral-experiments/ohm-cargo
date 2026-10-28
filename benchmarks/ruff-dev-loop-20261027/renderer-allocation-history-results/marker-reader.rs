use annotate_snippets::{AnnotationKind, Level, Patch, Renderer, Snippet};
fn main() {
    let source = "First line\r\nSecond oops line";
    let input = &[
        Level::ERROR.primary_title("oops").element(
            Snippet::source(source)
                .cell_index(Some(1))
                .annotation(AnnotationKind::Primary.span(19..23).label("oops")),
        ),
        Level::HELP
            .secondary_title("remove the entry")
            .element(
                Snippet::source(source)
                    .cell_index(Some(1))
                    .patch(Patch::new(19..24, "")),
            )
            .element(
                Snippet::source(source)
                    .cell_index(Some(1))
                    .patch(Patch::new(23..28, "")),
            ),
    ];
println!("{}",Renderer::plain().render(input));
}
