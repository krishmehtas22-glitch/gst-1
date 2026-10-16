# Reader 7.30: explicit single-PDF AI action

**Analyse ONE PDF with Groq** uses the focused selected row even if a previous
Ctrl+A selection remains. With no selected focus, it requires exactly one selected
row. Ambiguous multiple selections start nothing. Confirmation names the PDF and
caps new AI attempts across providers at one. Cancellation starts nothing.

The existing **Analyse selected PDFs** action remains for deliberate multiple-PDF
selection. The client-batch action remains separate. Startup and watching only
list files. Saved successful reads and human approvals still consume no new AI
attempt; a single-PDF status explicitly reports the new-attempt count and filename.

The existing selected workflow regenerates complete client XML from saved/local
data. Several XML vouchers are not evidence of several API calls. The new status
separates those counts. Tests record the requested source digest: selecting one
PDF from a three-PDF client produces exactly one mocked Groq request and three
client XML vouchers; the other two PDFs receive no new AI request. UI tests cover
100 selected rows with only one focused target, cancellation and stale/no focus.

Groq prompts/extraction, Common_Rules backend files, manual review, UQC, XML writers
and Import ALL are unchanged from Reader 7.29. The update changes the desktop UI
only and reuses the existing path filter and request budget. No live paid AI calls
or Tally imports are used to test/install this update.
