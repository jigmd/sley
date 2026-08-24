from sley import Flow, node


@node
def text_input(context):
    if "text" not in context.state:
        context.state["text"] = input("\nEnter text to convert: ")

    print("\nChoose transformation:")
    print("1. Convert to UPPERCASE")
    print("2. Convert to lowercase")
    print("3. Reverse text")
    print("4. Remove extra spaces")
    print("5. Exit")

    choice = input("\nYour choice (1-5): ")
    if choice == "5":
        # end() finishes this branch instead of following its unlabelled link.
        context.end()
        return

    context.state["choice"] = choice


@node
def text_transform(context):
    text = context.state["text"]
    choice = context.state["choice"]

    if choice == "1":
        result = text.upper()
    elif choice == "2":
        result = text.lower()
    elif choice == "3":
        result = text[::-1]
    elif choice == "4":
        result = " ".join(text.split())
    else:
        result = "Invalid option!"

    print("\nResult:", result)

    if input("\nConvert another text? (y/n): ").lower() == "y":
        del context.state["text"]
    else:
        context.end()


# A normal return follows each node's unlabelled link.
text_input.link(text_transform)
text_transform.link(text_input)

flow = Flow(text_input)
