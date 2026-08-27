import yaml
from sley import Context, ScopeResult
from utils import call_llm


def _yaml_block(response: str, label: str) -> dict:
    if "```yaml" not in response:
        raise ValueError(f"{label} must contain a YAML block")
    parsed = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a YAML object")
    return parsed


async def plan_brief(context: Context) -> None:
    sources = context.state["sources"]
    response = await call_llm(
        f"""
Create a plan for a source-grounded comparison brief.

Question: {context.state["question"]}

Available source notes:
{yaml.safe_dump(sources, sort_keys=False)}

Return exactly:
```yaml
foundation:
  audience: one concrete audience
  thesis: one sentence shared by every section
  required_terms:
    - term used consistently
sections:
  - id: stable-section-id
    goal: one independently judgeable goal
    source_ids:
      - allowed-source-id
```

Return two or three sections. Use only source IDs present above.
"""
    )
    plan = _yaml_block(response, "plan")
    foundation = plan.get("foundation")
    sections = plan.get("sections")
    if not isinstance(foundation, dict) or not isinstance(sections, list):
        raise ValueError("plan is missing foundation or sections")
    required_terms = foundation.get("required_terms")
    if (
        not isinstance(foundation.get("audience"), str)
        or not foundation["audience"].strip()
        or not isinstance(foundation.get("thesis"), str)
        or not foundation["thesis"].strip()
        or not isinstance(required_terms, list)
        or not required_terms
        or not all(isinstance(term, str) and term.strip() for term in required_terms)
    ):
        raise ValueError("foundation is missing audience, thesis, or required terms")
    if not 2 <= len(sections) <= 3:
        raise ValueError("plan must contain two or three sections")

    known_sources = set(sources)
    seen_ids = set()
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("each section must be an object")
        section_id = section.get("id")
        goal = section.get("goal")
        source_ids = section.get("source_ids")
        if (
            not isinstance(section_id, str)
            or not section_id
            or section_id in seen_ids
            or not isinstance(goal, str)
            or not goal
            or not isinstance(source_ids, list)
            or not source_ids
            or not all(isinstance(source_id, str) for source_id in source_ids)
            or not set(source_ids) <= known_sources
        ):
            raise ValueError("section IDs, goals, and source IDs must be valid")
        seen_ids.add(section_id)

    context.state["foundation"] = foundation
    context.state["plan"] = sections
    print(f"Planner froze the foundation and created {len(sections)} sections")
    context.emit("build", sections)


def dispatch_sections(context: Context) -> None:
    for section in context.input:
        context.emit("write", section)


async def write_section(context: Context) -> None:
    section = context.input
    sources = {
        source_id: context.state["sources"][source_id]
        for source_id in section["source_ids"]
    }
    response = await call_llm(
        f"""
Write one section of a source-grounded comparison brief.

Shared foundation:
{yaml.safe_dump(context.state["foundation"], sort_keys=False)}

Section assignment:
{yaml.safe_dump(section, sort_keys=False)}

Allowed source notes:
{yaml.safe_dump(sources, sort_keys=False)}

Return exactly:
```yaml
section_id: stable-section-id
draft: concise section text with inline [source-id] citations
citations:
  - source-id
```
"""
    )
    result = _yaml_block(response, "worker result")
    citations = result.get("citations")
    if (
        result.get("section_id") != section["id"]
        or not isinstance(result.get("draft"), str)
        or not result["draft"].strip()
        or not isinstance(citations, list)
        or not citations
        or not all(isinstance(citation, str) for citation in citations)
        or not set(citations) <= set(section["source_ids"])
    ):
        raise ValueError("worker result does not match its assignment")
    print(f"Worker completed {section['id']}")
    context.end(result)


def collect_sections(context: Context, result: ScopeResult) -> None:
    sections = sorted(result.outputs, key=lambda section: section["section_id"])
    context.emit(input=sections)


async def edit_brief(context: Context) -> None:
    response = await call_llm(
        f"""
Integrate independently written sections into one coherent comparison brief.

Question: {context.state["question"]}

Frozen foundation:
{yaml.safe_dump(context.state["foundation"], sort_keys=False)}

Sections:
{yaml.safe_dump(context.input, sort_keys=False)}

Preserve supported inline citations. Remove duplicated claims, reconcile
terminology, and return only the final brief.
"""
    )
    if not response.strip():
        raise ValueError("editor returned an empty brief")
    context.state["final_brief"] = response.strip()
    print("Integration editor completed the brief")
