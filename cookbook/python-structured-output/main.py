import asyncio
from pathlib import Path

import yaml
from sley import Context, Flow, RetryPolicy, node
from utils import call_llm


@node(retry=RetryPolicy(max_attempts=3, delay_ms=10_000))
def parse_resume(context: Context) -> None:
    resume = context.state["resume_text"]
    skills = context.state["target_skills"]
    numbered_skills = "\n".join(
        f"{index}: {skill}" for index, skill in enumerate(skills)
    )
    prompt = f"""
Analyze the resume below. Return only a YAML code block.

Resume:
{resume}

Target skills (return matching indexes):
{numbered_skills}

Extract `name`, `email`, `experience`, and `skill_indexes`.

Use this shape:
```yaml
name: Jane Doe
email: jane@example.com
experience:
  - title: Manager
    company: Corp A
skill_indexes:
  - 0
```
"""

    response = call_llm(prompt)
    if "```yaml" not in response:
        raise ValueError("response must contain a YAML block")

    parsed = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    required = {"name", "email", "experience", "skill_indexes"}
    if not isinstance(parsed, dict) or not required <= parsed.keys():
        raise ValueError("response is missing required resume fields")
    if not all(
        isinstance(parsed[field], str) and parsed[field].strip()
        for field in ("name", "email")
    ):
        raise ValueError("name and email must be non-empty text")
    if not isinstance(parsed["experience"], list) or not all(
        isinstance(item, dict)
        and all(
            isinstance(item.get(field), str) and item[field].strip()
            for field in ("title", "company")
        )
        for item in parsed["experience"]
    ):
        raise TypeError("experience must contain title and company text")
    if not isinstance(parsed["skill_indexes"], list) or not all(
        isinstance(index, int)
        and not isinstance(index, bool)
        and 0 <= index < len(skills)
        for index in parsed["skill_indexes"]
    ):
        raise ValueError("skill_indexes must refer to the supplied target skills")
    if len(set(parsed["skill_indexes"])) != len(parsed["skill_indexes"]):
        raise ValueError("skill_indexes must not contain duplicates")

    # Validate the complete model result before publishing it to run state.
    context.state["structured_data"] = parsed


resume_flow = Flow(parse_resume)


def read_resume() -> str:
    return Path("data.txt").read_text(encoding="utf-8")


async def main() -> None:
    print("=== Resume Parser - Structured Output with Indexes & Comments ===\n")
    target_skills = [
        "Team leadership & management",
        "CRM software",
        "Project management",
        "Public speaking",
        "Microsoft Office",
        "Python",
        "Data Analysis",
    ]

    state = await resume_flow.run(
        {"resume_text": read_resume(), "target_skills": target_skills}
    )
    structured_data = state["structured_data"]

    print("\n=== STRUCTURED RESUME DATA (Comments & Skill Index List) ===\n")
    print(yaml.dump(structured_data, sort_keys=False, allow_unicode=True))
    print("✅ Extracted resume information.")
    print("\n--- Found Target Skills (from Indexes) ---")
    for index in structured_data["skill_indexes"]:
        if 0 <= index < len(target_skills):
            print(f"- {target_skills[index]} (Index: {index})")
    print("----------------------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
