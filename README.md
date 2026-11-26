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

Some scripts require third-party Python packages, including `lxml`, `python-docx`, and `reportlab`. The repository does not provide an automated dependency installation setup. The test results below should not be interpreted as a successful validation of this release.

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

During publication preparation, the following suites were attempted using Python 3.10.11 on Windows:

| Suite | Result |
|---|---|
| `python3 -I scripts/run_tests.py` | Stopped because `lxml` was unavailable. |
| `python3 -I scripts/run_v5_tests.py` | Stopped because `lxml` was unavailable. |
| `python3 -I scripts/run_pipeline_tests.py` | Stopped because `lxml` was unavailable. |
| `python3 -I tests/kb/run_kb_tests.py` | Reported import-test failures, then stopped because `reportlab` was unavailable. |

No passing test totals were established in that environment. Code was not modified to address these results. The ten example DOCX containers and their XML entries were readable; visual rendering in Microsoft Word has not been verified.

## Known limitations

- A verification result of PASS does not establish legal correctness or suitability for practice. Independent verification may use models from the same model family.
- Some scripts have known dependencies on contract types or document formatting, including report generation's dependency on `judgment_label`, false detection of article numbers from external statutes, and count validation for DOCX files with existing comments.
- Opening and displaying the Word files in Microsoft Word on a real device has not been verified.

## License

MIT License; see [LICENSE](LICENSE). The legal cache in `legal_cache/` is not a primary source and comes without warranty.
