"""Worker processes running engine jobs in scratch directories, with
cancellation, timeouts and respawn (PLAN.md 3.3). Returns arrays and
metadata, never widgets or figures.

client.py and protocol.py run in the UI process (no pyqula, no engine);
process.py is the worker's entry point and imports the engine inside main().
"""
