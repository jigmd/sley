from caskada import Flow
from nodes import apply_style, generate_outline, write_content

# A successful node with no emission follows its unlabelled link.
generate_outline.link(write_content)
write_content.link(apply_style)

article_flow = Flow(generate_outline)
