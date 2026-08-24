from nodes import dispatch_pdfs, process_pdf
from sley import Context, Flow, ScopeResult


def collect_results(context: Context, result: ScopeResult) -> None:
    context.state["results"] = list(result.outputs)
    # Zero emissions preserve the workers' hard End terminals after aggregation.


dispatch_pdfs.link(process_pdf, "process")
vision_flow = Flow(dispatch_pdfs, combine=collect_results)
