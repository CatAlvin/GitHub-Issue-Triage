# Verification record

Date: 2026-11-12. Python: 3.12.1. Local operating system: Windows.

| Check | Result | Reproduce |
| --- | --- | --- |
| Python unit and integration suite | 21 tests passed | `python scripts/verify.py` |
| HTTP and MCP schemas | Match runtime | `python scripts/contracts.py` |
| HTTP service and authentication | Passed | `python scripts/smoke_http.py` |
| Markdown rendering | 2 tests passed | `node --test tests/markdown.test.cjs` |
| Frontend syntax | Passed | `node --check web/app.js` |
| Figures and source metrics | Match bundled data | `python scripts/readme_assets.py --check` |
| Repository-local documentation links | Valid | `python scripts/check_docs.py` |

The [CI workflow](../.github/workflows/ci.yml) runs the same checks on Ubuntu and Windows. GitHub displays the result for each pushed commit in the repository's Actions tab.

The [metrics file](assets/metrics.json) records dataset counts, document chunks, test-module counts and MCP tool names. The figure script reads the bundled dataset, knowledge documents, tests and API contract to rebuild the assets.

The workbench was also checked in a browser at desktop, 820px, 390px and 320px widths. Search, filters, source reading, dialog dismissal, theme switching and JSON export were exercised. Screenshots are kept in [assets/](assets/). Detailed UI acceptance criteria are in the [workbench specification](../specs/workbench.md).

