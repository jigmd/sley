---
title: 'LLM Calls'
machine-display: false
---

# LLM Calls

Put model SDK calls behind an application-owned interface. Caskada does not
require or provide an LLM wrapper.

## Define the Application Contract

Prefer a function named after the job it performs:

```python
from typing import Protocol


class AnswerModel(Protocol):
    async def answer(self, question: str, sources: list[str]) -> str: ...
```

```typescript
interface AnswerModel {
  answer(question: string, sources: readonly string[]): Promise<string>
}
```

The concrete implementation may call a hosted provider, a local model, or a
test fake. It should own model selection, request formatting, provider timeout,
and response extraction.

## Call It from a Node

{% tabs %}
{% tab title="Python" %}

```python
from caskada import Flow, node


def create_answer_flow(model):
    async def answer(context):
        response = await model.answer(
            context.state["question"],
            context.state.get("sources", []),
        )
        context.state["answer"] = response

    return Flow(node(answer, name="answer"))
```

{% endtab %}
{% tab title="TypeScript" %}

```typescript
import { Flow, node } from 'caskada'

interface State {
  question: string
  sources?: string[]
  answer?: string
}

function createAnswerFlow(model: AnswerModel): Flow<State> {
  const answer = node<State>(async (context) => {
    context.state.answer = await model.answer(context.state.question, context.state.sources ?? [])
  })

  return new Flow(answer)
}
```

{% endtab %}
{% endtabs %}

The ordinary zero-emission return exits this one-node Flow. The model call does
not need to know about Context or graph topology.

## Operational Rules

- Set a provider-side request timeout; Caskada does not interrupt synchronous
  blocking code.
- Decide whether provider retries or Caskada whole-handler retries own each
  failure. Avoid unbounded stacked retry policies.
- Parse and validate structured model output before committing state.
- Use idempotency keys for model APIs that can create durable side effects.
- Keep prompts and response objects out of logs unless their data policy permits
  it.
- Use a deterministic fake in workflow tests.

See the agent, structured-output, and RAG cookbook projects for larger patterns.
