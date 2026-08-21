from caskada import Context, node
from utils import get_user_input, load_recipes


@node
async def fetch(context: Context) -> None:
    ingredient = await get_user_input("Enter ingredient: ")
    context.state["ingredient"] = ingredient
    context.state["recipes"] = await load_recipes(ingredient)
    context.emit("suggest")


@node
def suggest(context: Context) -> None:
    recipes = context.state["recipes"]
    index = context.state.get("suggestion_index", 0)
    context.state["suggestion"] = recipes[index % len(recipes)]
    context.state["suggestion_index"] = index + 1
    print(f"\nHow about: {context.state['suggestion']}")
    context.emit("approve")


@node
async def approve(context: Context) -> None:
    answer = await get_user_input("\nAccept this recipe? (y/n): ")
    if answer != "y":
        print("\nLet's try another recipe...")
        context.emit("retry")
        return

    print("\nGreat choice! Here's your recipe...")
    print(f"Recipe: {context.state['suggestion']}")
    print(f"Ingredient: {context.state['ingredient']}")
    # No emission means this branch leaves the Flow normally.
