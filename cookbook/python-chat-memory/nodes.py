from sley import Context, node
from utils.call_llm import call_llm
from utils.get_embedding import get_embedding
from utils.vector_index import add_vector, create_index, search_vectors


@node
def read_question(context: Context) -> None:
    messages = context.state.setdefault("messages", [])
    if not messages:
        print("Welcome to the interactive chat! Type 'exit' to end the conversation.")

    question = input("\nYou: ")
    if question.lower() == "exit":
        print("\nGoodbye!")
        return

    messages.append({"role": "user", "content": question})
    context.emit("retrieve", question)


@node
def retrieve_memory(context: Context) -> None:
    question = context.input
    index = context.state.get("vector_index")
    conversations = context.state.get("vector_items", [])

    retrieved = None
    if index is not None and conversations:
        print(f"🔍 Finding relevant conversation for: {question[:30]}...")
        indices, distances = search_vectors(index, get_embedding(question), k=1)
        if indices:
            retrieved = conversations[indices[0]]
            print(f"📄 Retrieved conversation (distance: {distances[0]:.4f})")

    context.emit("answer", retrieved)


@node
def answer_question(context: Context) -> None:
    messages = context.state["messages"]
    recent_messages = messages[-6:]
    retrieved = context.input

    prompt_messages = []
    if retrieved:
        prompt_messages.append(
            {
                "role": "system",
                "content": "A relevant past conversation follows:",
            }
        )
        prompt_messages.extend(retrieved)
        prompt_messages.append(
            {"role": "system", "content": "Now continue the current conversation:"}
        )
    prompt_messages.extend(recent_messages)

    response = call_llm(prompt_messages)
    print(f"\nAssistant: {response}")
    messages.append({"role": "assistant", "content": response})

    if len(messages) > 6:
        oldest_pair = messages[:2]
        context.state["messages"] = messages[2:]
        context.emit("archive", oldest_pair)
        return

    context.emit("continue")


@node
def archive_memory(context: Context) -> None:
    conversation = context.input
    text = " ".join(
        f"{message['role']}: {message['content']}" for message in conversation
    )
    embedding = get_embedding(text)

    index = context.state.get("vector_index")
    if index is None:
        index = create_index(len(embedding))
        context.state["vector_index"] = index
    conversations = context.state.setdefault("vector_items", [])
    position = add_vector(index, embedding)
    conversations.append(conversation)

    print(f"✅ Added conversation to index at position {position}")
    print(f"✅ Index now contains {len(conversations)} conversations")
    context.emit("continue")
