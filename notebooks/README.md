# notebooks/

Scratch exploration only. Nothing here is part of the pipeline and nothing here
is expected to reproduce.

Anything worth keeping should move into `scripts/` as a deterministic script
that reads its settings from `config/` or the command line — the reason being
that a notebook's output depends on the order cells happened to be run in, which
is exactly the property a result being audited must not have.

Notebooks are gitignored except this file.
