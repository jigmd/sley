from tools.crawler import WebCrawler
from tools.parser import analyze_site


def crawl_website(context):
    base_url = context.state["base_url"]
    if not base_url:
        context.emit(input=[])
        return

    crawler = WebCrawler(
        base_url,
        context.state.get("max_pages", 10),
    )
    context.emit(input=crawler.crawl())


def dispatch_pages(context):
    if not context.input:
        # end() keeps an empty fan-out from creating an implicit unlabelled branch.
        context.end()
        return

    for page in context.input:
        context.emit("page", page)


def analyze_page(context):
    context.end(analyze_site(context.input))


def generate_report(context):
    pages = context.input
    if not pages:
        context.state["report"] = "No results to report"
        return

    report = ["Analysis Report\n", f"Total pages analyzed: {len(pages)}\n"]

    for page in pages:
        report.append(f"\nPage: {page['url']}")
        report.append(f"Title: {page['title']}")

        analysis = page.get("analysis", {})
        report.append(f"Summary: {analysis.get('summary', 'N/A')}")
        report.append(f"Topics: {', '.join(analysis.get('topics', []))}")
        report.append(f"Content Type: {analysis.get('content_type', 'unknown')}")
        report.append("-" * 80)

    context.state["report"] = "\n".join(report)
