import textwrap

import yaml
from utils import call_llm


def format_plan(plan_items, indent_level=0):
    indent = "  " * indent_level
    output = []

    if isinstance(plan_items, list):
        for item in plan_items:
            if isinstance(item, dict):
                status = item.get("status", "Unknown")
                description = item.get("description", "No description")
                result = item.get("result", "")
                mark = item.get("mark", "")

                line = f"{indent}- [{status}] {description}"
                if result:
                    line += f": {result}"
                if mark:
                    line += f" ({mark})"
                output.append(line)

                if item.get("sub_steps"):
                    output.append(format_plan(item["sub_steps"], indent_level + 1))
            else:
                output.append(f"{indent}- {item}")
    elif isinstance(plan_items, str):
        output.append(f"{indent}{plan_items}")
    else:
        output.append(f"{indent}# Invalid plan format: {type(plan_items)}")

    return "\n".join(output)


def format_plan_for_prompt(plan_items, indent_level=0):
    indent = "  " * indent_level
    output = []

    if isinstance(plan_items, list):
        for item in plan_items:
            if isinstance(item, dict):
                status = item.get("status", "Unknown")
                description = item.get("description", "No description")
                output.append(f"{indent}- [{status}] {description}")
                if item.get("sub_steps"):
                    output.append(
                        format_plan_for_prompt(item["sub_steps"], indent_level + 1)
                    )
            else:
                output.append(f"{indent}- {item}")
    else:
        output.append(f"{indent}{plan_items}")

    return "\n".join(output)


async def chain_of_thought(context):
    shared = context.state
    problem = shared.get("problem", "")
    thoughts = shared.get("thoughts", [])
    thought_number = shared.get("current_thought_number", 0) + 1

    if thoughts:
        thought_blocks = []
        for index, thought in enumerate(thoughts):
            number = thought.get("thought_number", index + 1)
            thinking = textwrap.dedent(thought.get("current_thinking", "N/A")).strip()
            plan = format_plan(thought.get("planning", []), indent_level=2)
            thought_blocks.append(
                f"Thought {number}:\n"
                f"  Thinking:\n{textwrap.indent(thinking, '    ')}\n"
                f"  Plan Status After Thought {number}:\n{plan}"
            )

        thoughts_text = "\n--------------------\n".join(thought_blocks)
        last_plan = thoughts[-1].get("planning", [])
    else:
        thoughts_text = "No previous thoughts yet."
        last_plan = [
            {"description": "Understand the problem", "status": "Pending"},
            {"description": "Develop a high-level plan", "status": "Pending"},
            {"description": "Conclusion", "status": "Pending"},
        ]

    last_plan_text = format_plan_for_prompt(last_plan)

    instruction_base = textwrap.dedent(
        f"""
            Your task is to generate the next thought (Thought {thought_number}).

            Instructions:
            1.  **Evaluate Previous Thought:** If not the first thought, start `current_thinking` by evaluating Thought {thought_number - 1}. State: "Evaluation of Thought {thought_number - 1}: [Correct/Minor Issues/Major Error - explain]". Address errors first.
            2.  **Execute Step:** Execute the first step in the plan with `status: Pending`.
            3.  **Maintain Plan (Structure):** Generate an updated `planning` list. Each item should be a dictionary with keys: `description` (string), `status` (string: "Pending", "Done", "Verification Needed"), and optionally `result` (string, concise summary when Done) or `mark` (string, reason for Verification Needed). Sub-steps are represented by a `sub_steps` key containing a *list* of these dictionaries.
            4.  **Update Current Step Status:** In the updated plan, change the `status` of the executed step to "Done" and add a `result` key with a concise summary. If verification is needed based on evaluation, change status to "Verification Needed" and add a `mark`.
            5.  **Refine Plan (Sub-steps):** If a "Pending" step is complex, add a `sub_steps` key to its dictionary containing a list of new step dictionaries (status: "Pending") breaking it down. Keep the parent step's status "Pending" until all sub-steps are "Done".
            6.  **Refine Plan (Errors):** Modify the plan logically based on evaluation findings (e.g., change status, add correction steps).
            7.  **Final Step:** Ensure the plan progresses towards a final step dictionary like `{{'description': "Conclusion", 'status': "Pending"}}`.
            8.  **Termination:** Set `next_thought_needed` to `false` ONLY when executing the step with `description: "Conclusion"`.
        """
    )

    if not thoughts:
        instruction_context = textwrap.dedent(
            """
                **This is the first thought:** Create an initial plan as a list of dictionaries (keys: description, status). Include sub-steps via the `sub_steps` key if needed. Then, execute the first step in `current_thinking` and provide the updated plan (marking step 1 `status: Done` with a `result`).
            """
        )
    else:
        instruction_context = textwrap.dedent(
            f"""
                **Previous Plan (Simplified View):**
                {last_plan_text}

                Start `current_thinking` by evaluating Thought {thought_number - 1}. Then, proceed with the first step where `status: Pending`. Update the plan structure (list of dictionaries) reflecting evaluation, execution, and refinements.
            """
        )

    instruction_format = textwrap.dedent(
        """
            Format your response ONLY as a YAML structure enclosed in ```yaml ... ```:
            ```yaml
            current_thinking: |
              # Evaluation of Thought N: [Assessment] ... (if applicable)
              # Thinking for the current step...
            planning:
              # List of dictionaries (keys: description, status, Optional[result, mark, sub_steps])
              - description: "Step 1"
                status: "Done"
                result: "Concise result summary"
              - description: "Step 2 Complex Task" # Now broken down
                status: "Pending" # Parent remains Pending
                sub_steps:
                  - description: "Sub-task 2a"
                    status: "Pending"
                  - description: "Sub-task 2b"
                    status: "Verification Needed"
                    mark: "Result from Thought X seems off"
              - description: "Step 3"
                status: "Pending"
              - description: "Conclusion"
                status: "Pending"
            next_thought_needed: true # Set to false ONLY when executing the Conclusion step.
            ```

            IMPORTANT: Make sure to:
            1. Use proper indentation (4 spaces) for all multi-line fields
            2. Use the | character for multi-line text fields
            3. Keep single-line fields without the | character
            4. Your answer must be wrapped in yaml code block or it will result in an error. Do not forget to include the ```yaml sequence at the beginning and end it with ```.
        """
    )

    prompt = textwrap.dedent(
        f"""
            You are a meticulous AI assistant solving a complex problem step-by-step using a structured plan. You critically evaluate previous steps, refine the plan with sub-steps if needed, and handle errors logically. Use the specified YAML dictionary structure for the plan.

            Problem: {problem}

            Previous thoughts:
            {thoughts_text}
            --------------------
            {instruction_base}
            {instruction_context}
            {instruction_format}
        """
    )

    response = call_llm(prompt)
    assert "```yaml" in response, "Response must contain yaml block"

    yaml_text = response.split("```yaml")[1].split("```")[0].strip()
    thought = yaml.safe_load(yaml_text)

    assert thought is not None, "YAML parsing failed, result is None"
    assert "current_thinking" in thought, "Missing 'current_thinking'"
    assert "next_thought_needed" in thought, "Missing 'next_thought_needed'"
    assert "planning" in thought, "Missing 'planning'"
    assert isinstance(thought["planning"], list), "'planning' must be a list"

    thought["thought_number"] = thought_number
    thinking = textwrap.dedent(thought["current_thinking"]).strip()
    plan = format_plan(thought["planning"], indent_level=1)

    if thought["next_thought_needed"]:
        print(f"\nThought {thought_number}:")
        print(textwrap.indent(thinking, "  "))
        print("\nCurrent Plan Status:")
        print(textwrap.indent(plan, "  "))
        print("-" * 50)
        context.emit("continue")
    else:
        print(f"\nThought {thought_number} (Conclusion):")
        print(textwrap.indent(thinking, "  "))
        print("\nFinal Plan Status:")
        print(textwrap.indent(plan, "  "))
        print("\n=== FINAL SOLUTION ===")
        print(thinking)
        print("======================\n")
        # Emitting nothing exits the root Flow and completes the run.

    # Keep state changes after the retryable model and parsing work.
    shared.setdefault("thoughts", []).append(thought)
    shared["current_thought_number"] = thought_number
    if not thought["next_thought_needed"]:
        shared["solution"] = thinking
