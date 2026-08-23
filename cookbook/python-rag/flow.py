from nodes import (
    create_index,
    embed_documents,
    embed_query,
    generate_answer,
    process_chunk_documents,
    retrieve_document,
)
from sley import Flow, node


def dispatch_documents(context):
    texts = context.state["texts"]
    if not texts:
        # No texts means zero branches; end() stops the unlabelled link running once.
        context.end()
        return

    for text in texts:
        context.emit("document", text)


def combine_documents(context, result):
    documents = result.outputs
    context.state["texts"] = [
        chunk for document in documents for chunk in document["chunks"]
    ]
    context.state["embeddings"] = [
        embedding for document in documents for embedding in document["embeddings"]
    ]

    if not documents:
        # No emission preserves the dispatcher's hard end, so index creation is skipped.
        return

    # One emission replaces all branch terminals with one downstream continuation.
    context.emit()


def get_offline_flow():
    dispatch = node(dispatch_documents)
    process = node(process_chunk_documents)
    embed = node(embed_documents)
    documents = Flow(dispatch, combine=combine_documents)
    build_index = node(create_index)

    dispatch.link(process, "document")
    process.link(embed)
    documents.link(build_index)
    return Flow(documents)


def get_online_flow():
    query = node(embed_query)
    retrieve = node(retrieve_document)
    answer = node(generate_answer)

    query.link(retrieve)
    retrieve.link(answer)
    return Flow(query)


offline_flow = get_offline_flow()
online_flow = get_online_flow()
