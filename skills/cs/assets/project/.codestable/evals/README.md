# Trusted evaluator boundary

`protocol.json` is protected and defines locked conditions, required splits, non-regression rules, and signed-result requirements.

Private held-out tasks and the evaluator implementation belong outside the candidate workspace. The project receives only an aggregate result signed with an evaluator-only HMAC key. `cs_eval.py import` verifies the immutable challenge digest and nonce, baseline version/content, candidate content/definition and overlay bytes, protocol hash, model/adapter/evaluator/budget locks, exact splits, result schema, and signature before the result can be used by `cs_evolve.py decide`.

Do not expose `CODESTABLE_EVALUATOR_KEY` to a candidate or normal `/cs` worker process.
