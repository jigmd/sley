# Structured Output

Model text is untrusted application data. Parse and validate it before changing
state or emitting control.

```python
@node
def decide(context):
    raw = call_model(build_prompt(context.state))
    decision = parse_decision(raw)

    # Keep state and control as the final commit block.
    context.state["reason"] = decision.reason
    context.emit(decision.action)
```

This ordering matters because retries repeat the whole handler and state writes
are not rolled back. If parsing fails before the commit block, a retry does not
observe half-applied decision state.

Static `TypedDict` or TypeScript interfaces improve author checking but do not
validate YAML, JSON, tool results, database rows, or values emitted by another
node. Use an ordinary parser or schema library at those boundaries.

When validation is substantial or reused, make it an explicit preparation node
and pass the validated value through `context.input`.

See [python-structured-output](../../cookbook/python-structured-output/) and
[python-thinking](../../cookbook/python-thinking/).
