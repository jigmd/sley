import yaml
from utils.call_llm import call_llm


def analyze_content(content):
    prompt = f"""
Analyze this webpage content:

Title: {content["title"]}
URL: {content["url"]}
Content: {content["text"][:2000]}  # Limit content length

Please provide:
1. A brief summary (2-3 sentences)
2. Main topics/keywords (up to 5)
3. Content type (article, product page, etc)

Output in YAML format:
```yaml
summary: >
    brief summary here
topics:
    - topic 1
    - topic 2
content_type: type here
```

IMPORTANT: Make sure to:
1. Use proper indentation (4 spaces) for all multi-line fields
2. Use the | character for multi-line text fields
3. Keep single-line fields without the | character
4. Your answer must be wrapped in yaml code block or it will result in an error. Do not forget to include the ```yaml sequence at the beginning and end it with ```.
"""

    response = call_llm(prompt)
    if "```yaml" not in response:
        raise ValueError("analysis must contain a YAML block")
    analysis = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(analysis, dict):
        raise ValueError("analysis must be a YAML mapping")
    if not isinstance(analysis.get("summary"), str):
        raise ValueError("analysis summary must be text")
    topics = analysis.get("topics")
    if not isinstance(topics, list) or not all(
        isinstance(topic, str) for topic in topics
    ):
        raise ValueError("analysis topics must be a list of text")
    if not isinstance(analysis.get("content_type"), str):
        raise ValueError("analysis content_type must be text")
    return analysis


def analyze_site(content):
    if not isinstance(content, dict) or not content.get("text"):
        raise ValueError("page content must include text")
    content["analysis"] = analyze_content(content)
    return content
