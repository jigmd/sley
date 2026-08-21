import asyncio
import json
from pathlib import Path


async def load_recipes(ingredient):
    """Read the local recipe catalog without blocking the event loop."""
    print(f"Loading recipes for {ingredient}...")
    text = await asyncio.to_thread(Path("recipes.json").read_text, encoding="utf-8")
    catalog = json.loads(text)
    recipes = catalog.get(ingredient.lower(), catalog["default"])
    print(f"Found {len(recipes)} recipes.")
    return recipes


async def get_user_input(prompt):
    """Read terminal input without blocking the event loop."""
    return (await asyncio.to_thread(input, prompt)).lower()
