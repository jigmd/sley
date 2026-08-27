import asyncio

import yaml
from sley import Context, Flow, node
from utils import call_llm


@node
def read_question(context: Context) -> None:
    messages = context.state.setdefault("messages", [])
    if not messages:
        print(
            "Welcome to the Travel Advisor Chat! Type 'exit' to end the conversation."
        )

    question = input("\nYou: ")
    if question.lower() == "exit":
        print("\nGoodbye! Safe travels!")
        return

    context.emit("validate", question)


@node
def validate_question(context: Context) -> None:
    question = context.input
    if not question or not question.strip():
        print(
            "\nTravel Advisor: Your query is empty. "
            "Please provide a travel-related question."
        )
        context.emit("retry")
        return

    if len(question.strip()) < 3:
        print(
            "\nTravel Advisor: Your query is too short. "
            "Please provide more details about your travel question."
        )
        context.emit("retry")
        return

    prompt = f"""
Evaluate if the following user query is related to travel advice, destinations,
planning, or other travel topics. The chat should reject off-topic, harmful, or
inappropriate queries.

User query: {question}

Return this YAML shape inside a ```yaml code block:
valid: true/false
reason: Explain why the query is valid or invalid
"""
    response = call_llm([{"role": "user", "content": prompt}])
    if "```yaml" not in response:
        raise ValueError("guardrail response must contain a YAML block")

    result = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if (
        not isinstance(result, dict)
        or type(result.get("valid")) is not bool
        or not isinstance(result.get("reason"), str)
        or not result["reason"].strip()
    ):
        raise ValueError("guardrail response needs a boolean valid and text reason")

    if not result["valid"]:
        print(f"\nTravel Advisor: {result['reason']}")
        context.emit("retry")
        return

    context.state["messages"].append({"role": "user", "content": question})
    context.emit("answer")


@node
def answer_question(context: Context) -> None:
    messages = context.state["messages"]
    if not messages or messages[0].get("role") != "system":
        messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "You are a helpful travel advisor. Only answer travel-related "
                    "questions. Keep responses informative, friendly, and under "
                    "100 words."
                ),
            },
        )

    response = call_llm(messages)
    print(f"\nTravel Advisor: {response}")
    messages.append({"role": "assistant", "content": response})
    context.emit("continue")


read_question.link(validate_question, "validate")
validate_question.link(read_question, "retry")
validate_question.link(answer_question, "answer")
answer_question.link(read_question, "continue")
travel_chat = Flow(read_question, max_activations=300)


async def main() -> None:
    await travel_chat.run({})


if __name__ == "__main__":
    asyncio.run(main())
