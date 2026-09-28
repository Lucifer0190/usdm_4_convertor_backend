Using your own reasoning below, return STRICT JSON only: a list with one object
per estimand, each shaped exactly as

{"name": "<estimand label as written, or empty string>",
 "population": {"value": "<value or null>", "quote": "<verbatim quote or empty>"},
 "variable": {"value": "<value or null>", "quote": "<verbatim quote or empty>"},
 "treatment": {"value": "<value or null>", "quote": "<verbatim quote or empty>"},
 "summary_measure": {"value": "<value or null>", "quote": "<verbatim quote or empty>"},
 "intercurrent_events": [
   {"text": "<the event>", "strategy": "<treatment policy | hypothetical | composite | while on treatment | principal stratum | empty>",
    "quote": "<verbatim quote naming the event and its strategy>"}
 ]}

Rules:
- Every "quote" MUST be an exact, character-for-character substring of the
  protocol text (copy-paste, not a paraphrase) — it will be verified by exact
  match, and an attribute whose quote does not match is discarded.
- An attribute the protocol does not state: "value": null, "quote": "".
- "strategy" must be empty unless the text names the strategy.
- If the protocol defines no estimands, return []. No prose outside the JSON.

YOUR REASONING:
{reasoning}

PROTOCOL TEXT:
{document_text}
