from caskada import Context, node


@node
def read_text(context: Context) -> None:
    text = input("Enter text (or 'q' to quit): ")
    if text == "q":
        return

    context.state["text"] = text
    stats = context.state.setdefault("stats", {"total_texts": 0, "total_words": 0})
    stats["total_texts"] += 1
    context.emit("count")


@node
def count_words(context: Context) -> None:
    context.state["stats"]["total_words"] += len(context.state["text"].split())
    context.emit("show")


@node
def show_stats(context: Context) -> None:
    stats = context.state["stats"]
    print("\nStatistics:")
    print(f"- Texts processed: {stats['total_texts']}")
    print(f"- Total words: {stats['total_words']}")
    print(
        f"- Average words per text: {stats['total_words'] / stats['total_texts']:.1f}\n"
    )
    context.emit("continue")
