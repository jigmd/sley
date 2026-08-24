# Conformance Coverage

| Case                       | RFC behavior                                    |
| -------------------------- | ----------------------------------------------- |
| `implicit_link`            | silent handler, unlabelled link, shared state   |
| `named_input`              | named routing and branch input                  |
| `unlabelled_input`         | unlabelled replacement input                    |
| `fanout_ends`              | fan-out and hard terminal outputs               |
| `output_presence`          | omitted output versus explicit null             |
| `combine_preserve`         | output projection and zero-emission combine     |
| `nested_combine`           | nested Flow join and replacement continuation   |
| `declared_exit`            | named Flow exit                                 |
| `unknown_action`           | fail-fast unknown route                         |
| `atomic_unknown`           | whole-buffer route validation                   |
| `retry`                    | whole-handler retry and failed-buffer discard   |
| `node_recovery`            | explicit Node recovery replacement              |
| `flow_recovery`            | settled terminals and Flow recovery replacement |
| `combine_recovery`         | failed combine result available to recovery     |
| `invalid_return`           | callback return validation                      |
| `activation_limit`         | local cycle guard                               |
| `local_concurrency`        | Flow-local callback width                       |
| `nested_end`               | hard End bypasses nested Flow links             |
| `nested_failure_terminals` | settled terminals from a failed child Flow      |
