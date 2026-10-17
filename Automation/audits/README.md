# BillSync acceptance audits

These checks deliberately go beyond the original regression examples. They test
the shipped implementation against independent expected behavior. **Failing
checks are confirmed findings, not expected passes or silently skipped tests.**

The 17 October 2026 audit tests source revision
`79dcfc4a5bcde30c9ece54194e47bfe7e0d2430e` (BillSync UI 2.2 / Reader 7.30).
See [the report](2026-10-17/REPORT.md) and its JSON/JUnit evidence.
No application, installer, extraction, financial, unit or import code was changed
as part of this audit. Documents and Tally snapshots in the added tests are
synthetic and are generated in disposable directories.

From the repository root, with the existing test environment:

```sh
python -m pytest Automation/tests -q --junitxml=regression.xml
python -m pytest Automation/audits/test_app_contracts.py -q -o junit_family=legacy --junitxml=acceptance.xml
python Automation/audits/ui_acceptance_probe.py --output=ui.json
```

The first and third commands need a desktop display (native Windows or a virtual
display on Linux). The input/output contract checks need the repository's normal
OCR and development dependencies. Run them in a fresh temporary test workspace,
not against client storage. Network connections are forbidden by the contract
tests; AI/Tally responses are controlled test doubles. No real provider key or
live Tally company is needed.

At the audited source revision, the acceptance command exits **1**, with 27
failed / 25 passed checks. This is historical evidence, not a passing release gate.
The later, separately authorized foreign-currency update addresses A05; its six
original currency checks pass. The subsequent exact-quantity update addresses
A04 by holding XML when a reused unit cannot represent every quantity. The later
user-approved A01 behavior is a nonblocking invoice-number/date warning per
client, retaining both uploads and vouchers; its original audit check passes.
The subsequent A02 role guard holds unsafe buyer/system ledger conflicts and
provides explicit local party review; the five original reserved-name checks pass.
The later PDF-only upload check addresses A07 by rejecting structurally unreadable
PDFs before storage; its original header-only acceptance check now passes.
Other
findings remain separate work, and the
historical report/JUnit files have not been rewritten. The existing
Windows workflow runs `Automation/tests`; it does not yet include these added
adversarial acceptance checks. A green historical Windows build therefore does
not mean the acceptance findings are fixed.

Five parameterized financial checks contain 500 distinct controlled invoice
records (100 per tax treatment). That is fixture coverage of XML/accounting
transfer, not 500 independently verified real-world AI extractions. Raster OCR
input fidelity is checked separately from transfer of a controlled correct AI
response, so input recognition errors cannot be confused with later XML errors.

The OCR ambiguity update adds bounded local second readings and persistent
source-review evidence, rather than promising perfect OCR. The strict primary
OCR fidelity check deliberately excludes appended alternate readings: the
historical Penci1 misspelling can still fail that strict check. New regression
checks in `tests/test_ocr_review_guard.py` verify real threshold OCR suggests
Pencil on PNG/JPG/JPEG fixtures, keeps the primary text, withholds numeric-conflict
alternatives from AI hints, retains warnings on cached results, and preserves
manual edits. Controlled AI response tests verify field transfer only, not live
Groq accuracy. Original audit reports remain unchanged.
