"""In-app help (decision 13.13, PLAN.md section 11 and phase 5, part 4):
pyqula's own user guide and docstrings, and guiqula's user guide for what is
guiqula's own, read without importing pyqula (the UI process never loads it,
13.15). guide.py splits a Markdown guide into sections; docstrings.py reads
pyqula's docstrings from its source; entries.py puts an entry's help
together. No Qt here: ui/help.py shows it."""
