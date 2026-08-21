import yaml
from caskada import Context, node
from utils import call_llm


@node
def generate_outline(context: Context) -> None:
    topic = context.state["topic"]
    response = call_llm(
        f"""
Create a simple outline for an article about {topic}.
Include at most 3 main sections and no subsections.

Return this YAML inside a ```yaml code block:

sections:
  - First section
  - Second section
  - Third section
"""
    )
    yaml_text = response.split("```yaml", 1)[1].split("```", 1)[0]
    outline = yaml.safe_load(yaml_text)
    sections = outline["sections"]

    context.state["sections"] = sections
    context.state["outline"] = "\n".join(
        f"{number}. {section}" for number, section in enumerate(sections, start=1)
    )

    print("\n===== OUTLINE =====\n")
    print(context.state["outline"])


@node
def write_content(context: Context) -> None:
    section_contents = {}
    for section in context.state["sections"]:
        section_contents[section] = call_llm(
            f"""
Write a short paragraph of at most 100 words about this section:

{section}

Use everyday language and include one brief example or analogy.
"""
        )

    context.state["section_contents"] = section_contents
    context.state["draft"] = "\n\n".join(
        f"## {section}\n\n{content}" for section, content in section_contents.items()
    )

    print("\n===== SECTION CONTENTS =====\n")
    for section, content in section_contents.items():
        print(f"--- {section} ---\n{content}\n")


@node
def apply_style(context: Context) -> None:
    context.state["final_article"] = call_llm(
        f"""
Rewrite this draft in a conversational, engaging style:

{context.state["draft"]}

Include a strong opening and conclusion.
"""
    )

    print("\n===== FINAL ARTICLE =====\n")
    print(context.state["final_article"])
