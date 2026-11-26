# commercial-legal-jp-extension

[日本語 / Japanese](README.ja.md)

An unofficial **verification extension for Japanese-law contract review**, designed to complement the **Commercial Legal** plugin in Claude for Legal. This project is not affiliated with Anthropic.

It leaves the Commercial Legal plugin unchanged and adds downstream verification of legal assessments and Word tracked changes.

> **Important:** This tool does not provide legal advice. Its outputs are mechanical consistency checks and AI-generated assessments, with no guarantee of legal accuracy. A human lawyer or legal professional must make the final legal decisions and approve the execution or delivery of contracts.

## Features

- Mechanically validate an initial contract review (`review.json`) against the original contract, facts, and primary legal sources: quotations, article numbers, numerical values, and applicability requirements.
- Run independent verification with the initial conclusions withheld, classify disagreements as factual, interpretive, or business decisions, and conduct adversarial review.
- Classify proposed revisions as verified changes, negotiation proposals, questions requiring confirmation, or prohibited changes; apply only eligible revisions as Word tracked changes and comments.
- Check Word consistency, including tracked-change and comment counts and whether body-text differences stay within the intended scope.
- Maintain a legal knowledge base with SQLite FTS5 and TF-IDF search, a hash-chained ledger, and an MCP server.

## Repository structure

| Directory | Contents |
|---|---|
| `scripts/` | Gates, verification, Word revision handling, and knowledge-base scripts. Primarily Python standard library, with third-party dependencies for some functions; run using `python3 -I`. |
| `agents/`, `skills/` | Agent definitions for independent verification and adversarial review, and review workflow skills. |
| `schemas/`, `specs/`, `config/`, `playbooks/` | JSON schemas, contract-type specifications, risk policies, and branching playbooks. |
| `docs/` | Review criteria, output formats, operating instructions, and knowledge-base specifications. |
| `examples/` | Sample contracts and review outputs described below. |
| `profile/` | Practice-profile **templates** to complete with your own information. |
| `legal_cache/` | Legal cache for testing. **Not a primary source**; refresh it using the retrieval scripts for actual use. |
| `tests/` | Tests using fictional data. |

Most supporting documentation, comments, and sample contracts are in Japanese. Preserve UTF-8 encoding, including Japanese filenames.

## Examples

All company names in the examples are fictional (Company A and Company B).

- `examples/contracts/`: sample contracts for review: `01_manufacturing` (master agreement for mold and plastic molding component manufacturing), `02_joint_research` (joint research and development agreement), and `03_cloud_service` (cloud service agreement).
- `examples/reviews/<contract>/custom_ai_internal.docx`: internal review produced by this system, with tracked changes and comments.
- `examples/reviews/<contract>/custom_ai_external.docx`: a version for the counterparty, with explanations phrased for that audience.
- `examples/reviews/02_joint_research/genspark_review.docx`: a review produced by another AI for comparison.

Review examples were anonymized from outputs obtained during actual testing. They reflect the version used at that time and may differ from the current version's output.

## Prerequisites

This extension is intended for use with Claude, including the Commercial Legal plugin in Claude for Legal. Users must obtain their own paid Claude plan; it is not included in this repository.

Some scripts require third-party Python packages, including `lxml`, `python-docx`, and `reportlab`; knowledge-base schema validation also uses `jsonschema`. The repository does not provide an automated dependency installation setup. Test outcomes are specific to the runtime environment, as described below.

## Workflow overview

1. Complete the templates in `profile/` and check that they load using `scripts/check_config.py`. The design prevents silently falling back to general criteria when the profile has not loaded.
2. Retrieve primary legal sources through the e-Gov Law API using `pc/fetch_legal_sources.py` or `scripts/fetch_egov.py`. **Always compare cached material with primary sources before use.**
3. Prepare `review.json` following [`docs/操作手順書.md`](docs/操作手順書.md) and [`docs/review_schema.md`](docs/review_schema.md). Run the workflow in this order:

```text
review_gate.py → blind_packet.py (independent verification)
→ compare_judgments.py → integrated_gate.py → revision_state.py
→ apply_revisions.py → validate_docx.py
```

## Validation status

### Author's environment

The author reports that the following suites passed in the author's environment, described by the author as a standard-library-only environment:

| Suite | Author-reported result |
|---|---|
| `python3 -I scripts/run_tests.py` | **46/46 passed** |
| `python3 -I scripts/run_v5_tests.py` | **31/31 passed** |
| `python3 -I scripts/run_pipeline_tests.py` | **37/37 passed** |
| `python3 -I tests/kb/run_kb_tests.py` | **80/80 passed** |

These are results from the author's environment. Available packages and runtime configuration are environment-specific; the dependency requirements above describe imports used by the supplied scripts.

### Codex environments

During initial publication preparation on Windows with Python 3.10.11, the first three suites stopped because `lxml` was unavailable. The knowledge-base suite reported import-test failures and then stopped because `reportlab` was unavailable. Those runs did not establish passing totals in that Codex environment.

A later review in a separate Codex Windows environment with Python 3.12 and additional dependencies produced the following results:

| Suite | Codex review result |
|---|---|
| `scripts/run_tests.py` | 45/45 automated checks passed; one manual persistence check remained unperformed. |
| `scripts/run_v5_tests.py` | 30/31 passed; the nested v4 suite reported failures. |
| `scripts/run_pipeline_tests.py` | Stopped with a Windows CP932 decoding error. |
| `tests/kb/run_kb_tests.py` | Stopped with an SQLite database-open error. |

The author-reported results and the Codex results above are separate, environment-specific observations. These Codex runs do not replace the author's passing results. Code was not modified for these runs. Passing these suites checks implemented behavior and does not establish legal accuracy or cover every edge case.

The ten example DOCX containers and their XML entries were readable; visual rendering in Microsoft Word has not been verified by Codex.

## Known limitations

- A verification result of PASS does not establish legal correctness or suitability for practice. Independent verification may use models from the same model family.
- Some scripts have known dependencies on contract types or document formatting, including report generation's dependency on `judgment_label`, false detection of article numbers from external statutes, and count validation for DOCX files with existing comments.
- Opening and displaying the Word files in Microsoft Word on a real device has not been verified.

## License

MIT License; see [LICENSE](LICENSE). The legal cache in `legal_cache/` is not a primary source and comes without warranty.
