from utils import call_llm, fixed_size_chunk, get_embedding


def process_chunk_documents(context):
    context.emit(input=fixed_size_chunk(context.input))


def embed_documents(context):
    chunks = context.input
    embeddings = [get_embedding(chunk) for chunk in chunks]

    print(f"✅ Created {len(embeddings)} document embeddings")
    context.end(
        {
            "embeddings": embeddings,
            "chunks": chunks,
        }
    )


def create_index(context):
    print("🔍 Creating search index...")
    context.state["index"] = context.state["embeddings"]
    print(f"✅ Index created with {len(context.state['index'])} vectors")


def embed_query(context):
    query = context.state["query"]
    print(f"🔍 Embedding query: {query}")
    context.state["query_embedding"] = get_embedding(query)


def retrieve_document(context):
    print("🔎 Searching for relevant documents...")
    query = context.state["query_embedding"]
    if not context.state["index"]:
        raise ValueError("cannot retrieve from an empty index")
    if any(len(candidate) != len(query) for candidate in context.state["index"]):
        raise ValueError("document and query embedding dimensions differ")
    distances = [
        sum((left - right) ** 2 for left, right in zip(query, candidate))
        for candidate in context.state["index"]
    ]
    best_index = min(range(len(distances)), key=distances.__getitem__)
    distance = distances[best_index]

    document = {
        "text": context.state["texts"][best_index],
        "index": best_index,
        "distance": distance,
    }
    context.state["retrieved_document"] = document

    print(
        "📄 Retrieved document "
        f"(index: {document['index']}, distance: {document['distance']:.4f})"
    )
    print(f'📄 Most relevant text: "{document["text"]}"')


def generate_answer(context):
    query = context.state["query"]
    document = context.state["retrieved_document"]
    prompt = f"""
Briefly answer the following question based on the context provided:
Question: {query}
Context: {document["text"]}
If the context does not answer the question, say that the supplied context is
insufficient. Do not add unsupported facts.
Answer:
"""

    answer = call_llm(prompt)
    context.state["generated_answer"] = answer
    print("\n🤖 Generated Answer:")
    print(answer)
