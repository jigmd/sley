from sley import Context, node
from tools.embeddings import get_embedding


@node
def embed_text(context: Context) -> None:
    context.state["embedding"] = get_embedding(context.state["text"])
