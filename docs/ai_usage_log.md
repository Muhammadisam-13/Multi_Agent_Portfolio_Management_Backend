# AI usage log

Record of generative-AI tool use, kept for the GenAI-use rubric item.

| Date | Tool | What it was used for | What the team reviewed / changed |
|---|---|---|---|
| 2026-10-11 | Claude Code (Claude Opus 5.5) | Retrieval plan steps 1-4: repo skeleton, `mizan/schemas.py`, fake fixtures (`tests/fixtures/evidence_items.jsonl`), `mizan/retrieval/bundle.py` (as-of + ticker filter), `tests/test_bundle.py` (15 tests). Also answered whether PSX Data Portal PDFs can be fetched automatically (no, not without written permission; see CLAUDE.md rule 3). | _to fill in after review_ |
| 2026-10-13 | Claude Code (Claude Opus 5.5) | Checked the PSX Terms of Use (psx.com.pk/psx/terms-of-use): automated tools/spiders and systematic retrieval need prior written permission; no research exemption found. Built `mizan/data/` (psxdata price loader with validation, PDF text extraction with PyMuPDF, drop-folder document loader, frozen snapshot writer, `build_snapshot` CLI) and tests (27 total). Smoke-ran psxdata live for OGDC, June 2025. | _to fill in after review_ |
| 2026-10-13 | Claude Code (Claude Opus 5.5) | After the team decision recorded in CLAUDE.md rule 3: removed the manual drop-folder path (`data/raw_documents/`, the uncommitted drop-folder loader `mizan/data/documents.py` and its tests), added `data/cache/` to `.gitignore`, created branch `retrieval/fetcher-and-search`. | _to fill in after review_ |
