# Reader 7.28: listing is free of AI requests

This supersedes the automatic-analysis behavior introduced in 7.27.

Opening the app, choosing a client/folder, changing a provider, refreshing and
watching for new PDFs only list filenames and filesystem metadata. These actions
do not read PDF contents, run OCR, call AI or generate XML. Newly arrived/changed
PDFs wait for the user's next explicit analysis choice. An unchanged analysed
row may retain its previously loaded display data in the same app session.

Select one or more rows (Ctrl/Shift or Ctrl+A) and choose `Analyse selected PDFs`.
The provider-specific selected actions use the same selection. A confirmation
states the exact PDF count and fresh-attempt cap. Cancelling makes no AI calls.
One selected PDF permits at most one fresh attempt; 100 permit at most 100 across
configured providers. This is a request cap, not a fixed currency price or a
guarantee that every attempt succeeds. Saved successes/approvals consume no new
attempts. The existing chosen-client batch actions also require confirmation.

Confirmed file paths are frozen. New files arriving before/during analysis are
not added to the upload scope. Stop prevents further calls; an in-flight request
may finish. When explicitly analysing a scope, AI extracts fields before Python
converts them through the existing client XML writer. Other client sources can
contribute saved/local data to the complete client review XML, but receive no
fresh AI requests. No automatic Tally imports occur.

Manual source correction/unit acceptance/test confirmation can revalidate locally
through Python without AI. The locked Import ALL action, UQC catalog, numeric
values, XML writers and Tally transports remain unchanged. The V3 prototype is
still separate. This change does not establish model extraction accuracy.

Close older reader windows before installing. Extract `Reader_7_28_Manual_AI_Update.zip`,
copy its three files beside the actual `Invoice_Desktop.py`/`Common_Rules` folder,
and double-click `Install_Reader_7_28.bat`. The installer prefers the main-folder
app over a nested Automation checkout, backs up known code, refuses unknown edits,
and sends no API/Tally calls itself. Restart using `Open_Invoice_App.bat` or the
reader virtual-environment Python and verify the title says Reader 7.28. A frozen
EXE needs a Windows rebuild; copying Python source cannot change an old EXE.
