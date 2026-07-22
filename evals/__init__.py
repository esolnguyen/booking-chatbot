"""Evaluation harness for the booking recommendation pipeline.

Two modes:
  * offline (default) — fakes the LLM agents and the vector store so the REAL
    router, policy/fact checkers, confidence caps and freshness all run with
    zero Azure cost. Used for routing precision/recall and CI regression gating.
  * live (--live)     — runs the real pipeline end to end against Azure OpenAI to
    measure grounding rate and whether the agent's own picks respect policy.
"""
