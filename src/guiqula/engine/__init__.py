"""Turns a Document into pyqula objects, with a content-hash cache per
pipeline prefix; seeds stochastic entries and hands out copies (PLAN.md 3.3).

Runs in the worker process, never in the UI process. Phase 1.
"""
