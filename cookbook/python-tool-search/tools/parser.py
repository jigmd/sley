import yaml
from utils.call_llm import call_llm


def analyze_results(query: str, results: list[dict]) -> dict:
    formatted = "\n".join(
        f"{index}. {result['title']}\n{result['snippet']}\n{result['link']}"
        for index, result in enumerate(results, 1)
    )
    prompt = f"""
Analyze these search results for the query "{query}":

{formatted}

Return a YAML code block with this shape:
```yaml
summary: brief summary
key_points:
  - point 1
follow_up_queries:
  - next query
```
"""
    response = call_llm(prompt)
    if "```yaml" not in response:
        raise ValueError("response must contain a YAML block")
    analysis = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(analysis, dict):
        raise TypeError("analysis must be a mapping")
    if not isinstance(analysis.get("summary"), str):
        raise TypeError("analysis summary must be text")
    for field in ("key_points", "follow_up_queries"):
        values = analysis.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise TypeError(f"analysis {field} must be a list of text")
    return analysis
