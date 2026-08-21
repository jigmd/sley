from caskada import Context, node
from tools.parser import analyze_results
from tools.search import search_web


@node
def search(context: Context) -> None:
    context.state["search_results"] = search_web(
        context.state["query"], context.state["num_results"]
    )


@node
def analyze(context: Context) -> None:
    results = context.state["search_results"]
    analysis = (
        analyze_results(context.state["query"], results)
        if results
        else {
            "summary": "No search results to analyze",
            "key_points": [],
            "follow_up_queries": [],
        }
    )
    context.state["analysis"] = analysis

    print("\nSearch Analysis:")
    print("\nSummary:", analysis["summary"])
    print("\nKey Points:")
    for point in analysis["key_points"]:
        print(f"- {point}")
    print("\nSuggested Follow-up Queries:")
    for query in analysis["follow_up_queries"]:
        print(f"- {query}")
