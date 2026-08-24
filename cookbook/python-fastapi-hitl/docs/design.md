# Design

The example has three workflow steps:

```text
process --> review --approved--> show_result
             |
             +--rejected--> process
```

- `process` performs the asynchronous work.
- `review` publishes an SSE update and waits for the shared review event.
- `show_result` is a normal leaf, so it emits nothing and exits the Flow.

The nested review channel is the bridge between HTTP requests and the active
Flow. Final application data comes from the state returned by `run()`.
