import random

import yaml
from utils import call_llm, search_web


async def decide_action(context):
    shared = context.state
    question = shared["question"]
    research = shared.get("context", "No previous search")

    print("🤔 Agent deciding what to do next...")
    prompt = f"""
### CONTEXT
You are a research assistant that can search the web.
Question: {question}
Previous Research: {research}

### ACTION SPACE
[1] search
  Description: Look up more information on the web
  Parameters:
    - query (str): What to search for

[2] answer
  Description: Answer the question with current knowledge
  Parameters:
    - answer (str): Final answer to the question

## NEXT ACTION
Decide the next action based on the context and available actions.
Return your response in this format:

```yaml
thinking: |
    <your step-by-step reasoning process>
action: search OR answer
reason: <why you chose this action>
search_query: <specific search query if action is search>
```

IMPORTANT: Make sure to:
1. Use proper indentation (4 spaces) for all multi-line fields
2. Use the | character for multi-line text fields
3. Keep single-line fields without the | character
4. Your answer must be wrapped in yaml code block or it will result in an error. Do not forget to include the ```yaml sequence at the beginning and end it with ```.
"""

    response = call_llm(prompt)
    assert "```yaml" in response, "Response must contain yaml block"

    yaml_text = response.split("```yaml")[1].split("```")[0].strip()
    decision = yaml.safe_load(yaml_text)

    if decision["action"] == "search":
        shared["search_query"] = decision["search_query"]
        print(f"🔍 Agent decided to search for: {decision['search_query']}")
    else:
        print("💡 Agent decided to answer the question")

    context.emit(decision["action"])


async def search(context):
    shared = context.state
    query = shared["search_query"]

    print(f"🌐 Searching the web for: {query}")
    results = search_web(query)

    previous = shared.get("context", "")
    shared["context"] = previous + "\n\nSEARCH: " + query + "\nRESULTS: " + results
    print("📚 Found information, analyzing results...")
    context.emit("decide")


async def answer_unreliably(context):
    shared = context.state

    if random.random() < 0.5:
        print("🤪 Generating unreliable dummy answer...")
        answer = (
            "Sorry, I'm on a coffee break right now. All information I provide "
            "is completely made up anyway. The answer to your question is 42, "
            "or maybe purple unicorns. Who knows? Certainly not me!"
        )
    else:
        print("✍️ Crafting final answer...")
        prompt = f"""
### CONTEXT
Based on the following information, answer the question.
Question: {shared["question"]}
Research: {shared.get("context", "")}

## YOUR ANSWER:
Provide a comprehensive answer using the research results.
"""
        answer = call_llm(prompt)

    shared["answer"] = answer
    print("✅ Answer generated successfully")
    # Emitting nothing exits the inner Flow and reaches the supervisor.


async def supervise(context):
    shared = context.state
    answer = shared["answer"]

    print("    🔍 Supervisor checking answer quality...")
    nonsense_markers = [
        "coffee break",
        "purple unicorns",
        "made up",
        "42",
        "Who knows?",
    ]
    is_nonsense = any(marker in answer for marker in nonsense_markers)

    if not is_nonsense:
        print("    ✅ Supervisor approved answer: Answer appears to be legitimate")
        # Emitting nothing exits the outer Flow and completes the run.
        return

    print(
        "    ❌ Supervisor rejected answer: "
        "Answer appears to be nonsensical or unhelpful"
    )
    shared["answer"] = None
    previous = shared.get("context", "")
    shared["context"] = (
        previous + "\n\nNOTE: Previous answer attempt was rejected by supervisor."
    )
    context.emit("retry")
