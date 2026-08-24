from nodes import analyze_page, crawl_website, dispatch_pages, generate_report
from sley import Flow, node


def combine_pages(context, result):
    # Replace every worker terminal with one input for the report node.
    context.emit(input=list(result.outputs))


def create_flow():
    crawl = node(crawl_website)
    dispatch = node(dispatch_pages)
    analyze = node(analyze_page)
    report = node(generate_report)

    dispatch.link(analyze, "page")
    analysis = Flow(dispatch, combine=combine_pages)

    crawl.link(analysis)
    analysis.link(report)

    return Flow(crawl)
