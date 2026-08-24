import faiss
import numpy as np
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
    embeddings = np.array(context.state["embeddings"], dtype=np.float32)
    dimension = embeddings.shape[1]

    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    context.state["index"] = index
    print(f"✅ Index created with {index.ntotal} vectors")


def embed_query(context):
    query = context.state["query"]
    print(f"🔍 Embedding query: {query}")
    context.state["query_embedding"] = np.array(
        [get_embedding(query)], dtype=np.float32
    )


def retrieve_document(context):
    print("🔎 Searching for relevant documents...")
    distances, indices = context.state["index"].search(
        context.state["query_embedding"], k=1
    )
    best_index = indices[0][0]

    document = {
        "text": context.state["texts"][best_index],
        "index": best_index,
        "distance": distances[0][0],
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
Answer:
"""

    answer = call_llm(prompt)
    context.state["generated_answer"] = answer
    print("\n🤖 Generated Answer:")
    print(answer)
