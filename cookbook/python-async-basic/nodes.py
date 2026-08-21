from caskada import Context, node
from utils import call_llm_async, fetch_recipes, get_user_input


@node
async def fetch(context: Context) -> None:
    ingredient = await get_user_input("Enter ingredient: ")
    context.state["ingredient"] = ingredient
    context.state["recipes"] = await fetch_recipes(ingredient)
    context.emit("suggest")


@node
async def suggest(context: Context) -> None:
    recipes = context.state["recipes"]
    context.state["suggestion"] = await call_llm_async(
        f"Choose best recipe from: {', '.join(recipes)}"
    )
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
