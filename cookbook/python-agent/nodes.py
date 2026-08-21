import yaml
from caskada import Context, node
from utils import call_llm, search_web


@node
def decide(context: Context) -> None:
    print("🤔 Agent deciding what to do next...")
    prompt = f"""
You are a research assistant that can search the web.
Question: {context.state["question"]}
Previous research: {context.state.get("research", "No previous search")}

### NEXT ACTION
Choose `search` or `answer` and return a YAML code block:
```yaml
action: search
search_query: what to search for
answer: final answer when action is answer
```
"""
    response = call_llm(prompt)
    if "```yaml" not in response:
        raise ValueError("decision must contain a YAML block")
    decision = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(decision, dict) or decision.get("action") not in {
        "search",
        "answer",
    }:
        raise ValueError("decision action must be search or answer")

    if decision["action"] == "search":
        context.state["search_query"] = decision["search_query"]
        print(f"🔍 Agent decided to search for: {decision['search_query']}")
    else:
        context.state["research"] = decision["answer"]
        print("💡 Agent decided to answer the question")
    context.emit(decision["action"])


@node
def search(context: Context) -> None:
    query = context.state["search_query"]
    print(f"🌐 Searching the web for: {query}")
    results = search_web(query)
    context.state["research"] = (
        context.state.get("research", "") + f"\n\nSEARCH: {query}\nRESULTS: {results}"
    )
    print("📚 Found information, analyzing results...")
    context.emit("decide")


@node
def answer(context: Context) -> None:
    print("✍️ Crafting final answer...")
    context.state["answer"] = call_llm(
        f"""
Answer this question using the research below.
Question: {context.state["question"]}
Research: {context.state.get("research", "")}
"""
    )
    print("✅ Answer generated successfully")
