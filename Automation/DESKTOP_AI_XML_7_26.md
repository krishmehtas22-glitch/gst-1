# Desktop Reader 7.26: selected AI reading prepares complete client XML

The selected-invoice AI action previously saved an extraction, then called the
strict desktop workflow. Unapproved AI warnings or test-PDF confirmation could
leave the table showing correct invoice values but zero prepared XML files.
The existing client-batch action already used the complete review-XML workflow.

The selected AI action now uses that same existing batch/checkpoint workflow.
It allows at most one new AI attempt for the selected PDF across configured
providers. Successful saved reads and human approvals are reused. The selected
client's other PDFs use saved/local reading, and the complete client Units.xml,
Masters.xml and Sales_Vouchers.xml are prepared even after AI failure or Stop.
Uncertainties remain in the existing Batch_Report.json and voucher narration;
this is neither human approval nor proof of financial correctness/Tally import.
Other client policies and exports are untouched.

The selected-action confirmation explains client-wide XML preparation. In test
mode it confirms only the selected PDF as test data; it does not approve the
invoice values or mark other client PDFs as individually confirmed. For all
client PDFs, use the existing `Read client batch with Groq -> XML` action.

Printed-unit metadata can be corrected without another AI call when the
production goods-table parser finds a complete matching table: name, HSN,
quantity, unit, rate and value must agree for every row. Only unit provenance
changes; manual corrections, selling symbols and all numeric values are retained.
Ambiguous, incomplete or mismatched tables keep their previous unit status.

Close the Python reader and run `py Apply_Desktop_AI_XML_7_26.py` in the existing
source folder. The installer accepts known Reader 7.25 source files, includes
the earlier production goods-table reading fix if needed, backs up replaced
code, and refuses unknown local edits. It does not scan invoices or contact
AI/Tally. Restart using the original Python launcher and check the window title
is `Reader 7.26`. A frozen EXE must be rebuilt on Windows to include this change.

The locked Import ALL method, its command/company routing, unit catalog,
unit normalizer, Tally transports and XML writers are unchanged. Existing saved
approvals, API results and financial/import history are not reset by installation.
The separate V3 evidence/teaching workflow remains separate from the desktop.

Validation reproduces the five Client 32 PDFs and saved results privately: the
old action has five read invoices and zero XML; the updated desktop action
prepares five vouchers/all three XML files, uses zero new AI calls, corrects
printed-unit labels and preserves financial values/human approval. Automated
tests also cover failed/limited AI, Stop, client isolation and GUI dispatch.
Neither mocked provider tests nor XML structural checks certify live AI accuracy
or successful import into a user's running Tally company.
