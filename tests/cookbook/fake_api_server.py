"""Small protocol-level fake for cookbook tests.

It deliberately implements only the OpenAI and Anthropic endpoints used by the
cookbooks. The examples still use their real SDKs; only the network boundary is
replaced.
"""

from __future__ import annotations

import io
import json
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

FIXTURE_TIMESTAMP = 1_700_000_000


def _flatten_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_flatten_content(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(_flatten_content(item) for item in value.values())
    return ""


def response_for(prompt: str) -> str:
    """Return deterministic content matching the schema requested by a prompt."""
    lowered = prompt.lower()

    if "write a customer-facing incident update" in lowered:
        if "no previous feedback" in lowered:
            return "Checkout was unavailable. We are investigating."
        return (
            "Checkout was unavailable from 14:05 to 14:23 UTC. "
            "Deployments remain paused while we investigate; there is no evidence "
            "of lost orders. The next update will be posted at 15:00 UTC."
        )
    if "act as an independent evaluator" in lowered:
        if "candidate:\ncheckout was unavailable. we are investigating." in lowered:
            return """```yaml
verdict: revise
summary: The update omits the exact time window and next update time.
findings:
  - criterion: State the exact time window.
    evidence: The candidate says only that checkout was unavailable.
    requested_change: Add 14:05 to 14:23 UTC.
  - criterion: State the next update time.
    evidence: No next update appears in the candidate.
    requested_change: Add the 15:00 UTC update time.
```"""
        return """```yaml
verdict: approved
summary: Every rubric criterion is supported by the supplied facts.
findings: []
```"""
    if "create a plan for a source-grounded comparison brief" in lowered:
        return """```yaml
foundation:
  audience: A small product team
  thesis: >-
    Use synchronous work for contested decisions and asynchronous work for
    durable context.
  required_terms:
    - synchronous
    - asynchronous
sections:
  - id: decision-speed
    goal: Explain when immediate exchange is worth its interruption cost.
    source_ids:
      - meeting-cost
      - decision-speed
  - id: written-record
    goal: Explain when durable written context is more useful.
    source_ids:
      - written-record
```"""
    if "write one section of a source-grounded comparison brief" in lowered:
        if "id: decision-speed" in lowered:
            return """```yaml
section_id: decision-speed
draft: >-
  Use synchronous discussion for ambiguous decisions that need immediate
  exchange [decision-speed], while accounting for its interruption cost
  [meeting-cost].
citations:
  - decision-speed
  - meeting-cost
```"""
        return """```yaml
section_id: written-record
draft: >-
  Use asynchronous proposals when the team needs durable context across
  schedules and time zones [written-record].
citations:
  - written-record
```"""
    if "integrate independently written sections" in lowered:
        return (
            "Cookbook integrated brief: use synchronous discussion for contested "
            "decisions [decision-speed] and asynchronous writing for durable context "
            "across schedules [written-record]."
        )
    if "create a substantially different candidate" in lowered:
        for angle, title in (
            ("direct", "Make the paths visible"),
            ("worked-example", "From callbacks to a graph"),
            ("checklist", "When a graph earns its place"),
            ("tradeoff-first", "Use topology only when it clarifies"),
        ):
            if f"candidate angle: {angle}" in lowered:
                return f"""```yaml
angle: {angle}
title: {title}
draft: Cookbook {angle} candidate with a materially distinct structure.
```"""
    if "judge two anonymous candidates" in lowered:
        return """```yaml
winner: A
evidence: Candidate A makes the maintenance consequence more concrete.
useful_element_from_loser: its concise closing sentence
```"""
    if "produce the final answer for this request" in lowered:
        return "Cookbook selected answer with one useful element integrated."
    if "reference-grounded quality loop component builder" in lowered:
        if "what sley owns" in lowered:
            return (
                "Cookbook candidate section: Sley schedules an in-process graph, "
                "while the application owns persistence and provider policy."
            )
        return (
            "Cookbook candidate section: begin with an ordinary function and add "
            "named links when workflow decisions need visible topology."
        )
    if "reference-grounded quality loop component judge" in lowered:
        winner = "A" if "artifact a:\ncookbook candidate section" in lowered else "B"
        return f"""```yaml
winner: {winner}
evidence: The candidate is at least as direct and decision-useful as the reference.
flip_condition: none
reachable: true
```"""
    if "reference-grounded quality loop integration editor" in lowered:
        return (
            "Cookbook benchmark candidate: Sley schedules an in-process graph while "
            "the application owns persistence. Start with an ordinary function and "
            "add named links when visible topology clarifies the workflow."
        )
    if "reference-grounded quality loop whole-artifact judge" in lowered:
        winner = "A" if "artifact a:\ncookbook benchmark candidate" in lowered else "B"
        return f"""```yaml
winner: {winner}
evidence: The candidate matches the reference on the ranked dimensions.
flip_condition: none
reachable: true
```"""
    if "iterative plan refinement" in lowered and "progress_summary" in lowered:
        return """```yaml
progress_summary: The smoke fixture completed and checked the plan.
plan:
  - step: Produce the fixture answer
    status: done
next_action: final
answer: Cookbook smoke solution
```"""
    if "extract `name`" in lowered and "skill_indexes" in lowered:
        return """```yaml
name: Jane Cookbook
email: jane@example.test
experience:
  - title: Engineer
    company: Sley
skill_indexes:
  - 5
  - 6
```"""
    if "create a simple outline" in lowered:
        return """```yaml
sections:
  - Why the topic matters
  - A practical example
  - What to do next
```"""
    if (
        "containing the sql query" in lowered
        or "containing the corrected sql" in lowered
    ):
        return """```yaml
sql: |
  SELECT category, COUNT(*) AS total_products FROM products GROUP BY category
```"""
    if "model context protocol" in lowered and "tool:" in lowered:
        return """```yaml
thinking: Use the addition tool.
tool: add
reason: The question asks for a sum.
parameters:
  a: 2
  b: 3
```"""
    if "evaluate if the following user query is related to travel" in lowered:
        return """```yaml
valid: true
reason: This is a travel-planning question.
```"""
    if "evaluate the following resume" in lowered and "candidate_name" in lowered:
        return """```yaml
candidate_name: Cookbook Candidate
qualifies: true
reasons:
  - Meets the education requirement
  - Has relevant experience
```"""
    if "analyze these search results" in lowered:
        return """```yaml
summary: Cookbook search summary
key_points:
  - The fake search result was parsed
  - The analysis flow completed
follow_up_queries:
  - sley examples
  - sley documentation
```"""
    if "analyze this webpage content" in lowered:
        return """```yaml
summary: Cookbook page summary
topics:
  - sley
  - testing
content_type: article
```"""
    if (
        "return strictly using the following yaml structure" in lowered
        and "answer: 0.123" in lowered
    ):
        return """```yaml
thinking: The fixture produces a stable answer.
answer: 0.5
```"""
    if "### next action" in lowered or "## next action" in lowered:
        return """```yaml
thinking: The fixture has enough context to answer directly.
action: answer
reason: No external search is necessary for the smoke test.
answer: Cookbook smoke response
search_query: sley smoke test
searchQuery: sley smoke test
```"""
    if "directly reply a single word" in lowered:
        return "nostalgic"
    if "generate hint for" in lowered:
        return "A fond backward feeling"
    if "please translate the following markdown" in lowered:
        return "# Sley\n\nTranslated cookbook smoke fixture.\n"

    return "Cookbook smoke response"


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24_000)
        wav.writeframes(b"\x00\x00" * 240)
    return buffer.getvalue()


class _Handler(BaseHTTPRequestHandler):
    server_version = "SleyCookbookFake/1"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        if self.path.endswith("/audio/speech"):
            self._json_body()
            audio = _wav_bytes()
            self.send_response(200)
            self.send_header("content-type", "audio/wav")
            self.send_header("content-length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
            return

        if self.path.endswith("/audio/transcriptions"):
            length = int(self.headers.get("content-length", "0"))
            self.rfile.read(length)
            self._send_json({"text": "cookbook voice fixture"})
            return

        body = self._json_body()

        if self.path.endswith("/embeddings"):
            inputs = body.get("input", "")
            count = len(inputs) if isinstance(inputs, list) else 1
            self._send_json(
                {
                    "object": "list",
                    "model": body.get("model", "fake-embedding"),
                    "data": [
                        {"object": "embedding", "index": index, "embedding": [0.1] * 8}
                        for index in range(count)
                    ],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                }
            )
            return

        messages = body.get("messages", [])
        prompt = _flatten_content(messages)
        content = response_for(prompt)

        if self.path.endswith("/messages"):
            blocks: list[dict[str, Any]] = []
            if body.get("thinking"):
                blocks.append(
                    {
                        "type": "thinking",
                        "thinking": "Fixture reasoning",
                        "signature": "fixture",
                    }
                )
            blocks.append({"type": "text", "text": content})
            self._send_json(
                {
                    "id": "msg_cookbook_fixture",
                    "type": "message",
                    "role": "assistant",
                    "model": body.get("model", "fake-anthropic"),
                    "content": blocks,
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )
            return

        if body.get("stream"):
            chunks = [
                content[index : index + 12] for index in range(0, len(content), 12)
            ]
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for chunk in chunks:
                event = {
                    "id": "chatcmpl-cookbook-fixture",
                    "object": "chat.completion.chunk",
                    "created": FIXTURE_TIMESTAMP,
                    "model": body.get("model", "fake-openai"),
                    "choices": [
                        {"index": 0, "delta": {"content": chunk}, "finish_reason": None}
                    ],
                }
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        self._send_json(
            {
                "id": "chatcmpl-cookbook-fixture",
                "object": "chat.completion",
                "created": FIXTURE_TIMESTAMP,
                "model": body.get("model", "fake-openai"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )


@contextmanager
def fake_api_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
