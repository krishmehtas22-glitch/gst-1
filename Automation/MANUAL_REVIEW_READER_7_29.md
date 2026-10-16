# Reader 7.29: simplified desktop and manual XML corrections

The app shows selected-PDF and client-batch Groq actions plus Stop. Gemini,
OpenRouter and GitHub controls/provider picker are removed. Their backend modules,
cache compatibility and existing AI extraction/fallback implementation are retained
unchanged. The separate Accept/change units, Recover processing lock and Confirm
test PDF buttons are removed.

Double-click an invoice to edit buyer/seller details, invoice fields and
line items, including units, quantities and rates. **Save changes to XML** saves
the digest-bound human review, enables the existing complete-client XML workflow,
and regenerates that client's Units.xml, Masters.xml and Sales_Vouchers.xml
locally. Other clients remain untouched. No provider request is sent.
A queued PDF can also be opened manually: the existing local reader loads saved
fields or Python extraction only on this explicit double-click. A PDF containing
independent invoices is expanded into separate rows for individual review. Existing
unit normalization and XML writers still apply (for example cm maps to CMS).

When Test invoices is enabled, the editor states that saving confirms the PDF as
fictional test data. Real documents require this mode to be unticked. Changed
source PDFs must be reread before the previous review can be saved.

Startup, refresh and watching remain filename/metadata listing only. AI actions
still need explicit selection and count confirmation. Import ALL and its locked
Tally/UQC implementation are unchanged. XML generation does not import to Tally.

The update changes only Invoice_Desktop.py for an existing 7.28 installation.
The installer also carries the exact prior reading files to support known earlier
source installations, without modifying their AI prompts or extraction logic.
