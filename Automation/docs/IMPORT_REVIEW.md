# Import review in BillSync UI 3.5

The review window appears before the current seller's units, masters or sales
vouchers are sent. Earlier seller groups may already have been imported; their
responses remain in Last_Tally_Import.json.

Select a row to see the complete reason, original source path and next step.
Open source PDF / image opens that exact document in the default viewer, even
when the extracted invoice number is blank or duplicated.

Edit invoice cancels all remaining imports and opens that invoice's editor.
Correct the printed fields, then Save changes to XML. Start Import to Tally
again when ready. This action does not make a new AI request.

Import to Tally anyway becomes available after the acknowledgement is selected.
It submits the existing values, including acknowledged data errors, without
inventing a missing invoice number/date or correcting GSTINs. Tally can reject
invalid or incomplete data. Decisions are recorded against this output and
company. Existing Manual Sales numbering and import-stage checks still apply.

Changed/missing source files, changed saved inputs or master snapshots and
unfinished AI extraction cannot be overridden. Restore/process the source or
save a reviewed correction and prepare fresh XML before importing.

Cancel import or the window's X stops all remaining seller groups. Cancellation
is not reported as a Tally failure and does not open the next group's review.
Completed earlier requests are not reversed. Check their receipts before a
manual retry. No automatic retries are sent.

The source/issue area scrolls; decision buttons stay in a fixed footer. The
company-selection window also scrolls separately from its import buttons.
