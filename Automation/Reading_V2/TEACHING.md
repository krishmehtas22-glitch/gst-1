# Teach the separate invoice reader

This feature saves your explicit reading instructions for future invoices.
It does not retrain a model or change the active desktop app, UQC policy,
financial XML writers or Import ALL. Teaching makes no AI requests.

After installing `Install_Invoice_Workflow_V3_2.py`, open Command Prompt in the
existing reader folder. Start with an example PDF:

```bat
.venv\Scripts\python.exe Teach_Invoice_Reader.py "F:\Downloads\dummy sales invoice\CLIENT 32\TEST-26-27-247_INTRA_Layout-1.pdf"
```

The command asks you to confirm the supplier, type a reading instruction, and
choose two or more unique printed first-page headings separated by `|`.
For this example, suitable headings are `Goods description | UOM`. A suitable
instruction is `Read the buyer under BUYER; SUPPLY DETAILS is not a buyer.
Use Qty for sold quantity and UOM for its printed selling unit.` Do not type
old amounts, quantities, GST rates, credentials or instructions to skip checks.

For noninteractive use:

```bat
.venv\Scripts\python.exe Teach_Invoice_Reader.py "example.pdf" --supplier "Example Supplies" --anchor "Consignee" --anchor "Delivered Qty" --instruction "Use Consignee as a buyer-location hint; verify the buyer role. Use Delivered Qty for sold quantities."
```

Those example names/headings must actually occur on the chosen PDF. The command
requires a verified seller in the first-page header and at least two unique
headings. If it cannot verify them, no lesson is saved. Use a clearer example
or review the supplier identity first. This initial version supports literal
headings and a small coordinate tolerance, not arbitrary visual similarity.

Instructions are stored in the reader's `.invoice_app/reading_guidance.json`.
The library contains supplier identity, heading positions, your instruction and
the example SHA256; it does not copy the example's financial values. Supplier
identity and printed GSTIN status must match exactly. Missing GSTIN does not
match a supplier rule that was taught with a GSTIN. Separate known GSTINs never
share a rule. Only enabled rules are considered.

Read future PDFs using the same separate workflow:

```bat
.venv\Scripts\python.exe Read_Invoice_V3.py "F:\Downloads\dummy sales invoice\NEW CLIENT" --xml --ai-provider Groq --max-ai-requests 50
```

A matched rule is included in a new AI extraction request, even when basic
local checks passed. All source-token checks, quantity/rate preservation,
request limits, quota fallback and review requirements still apply. Instructions
are hints, not permission to fabricate values or change tax treatment. New AI
reads use the new PDF's values. A changed layout or overlapping rules are
flagged for review; no conflicting instructions are chosen automatically.

Successful saved reads, including the separate AI cache, and human approvals
remain terminal. Teaching does not force another API call for an already-read
PDF. Test the effect on a genuinely new invoice. Reports distinguish a matched
rule from a rule actually sent in a new request; a retained cache reports the
IDs used when that result was originally generated. If no provider/key/budget
is available, no guided AI analysis occurs; separate review XML can still be
prepared from local/saved reading. No live Tally imports are sent.

Manage rules using:

```bat
.venv\Scripts\python.exe Teach_Invoice_Reader.py --list
.venv\Scripts\python.exe Teach_Invoice_Reader.py --disable RULE_ID
```

To change a rule, run the teaching command on an example again with
`--replace RULE_ID` plus the new instruction and anchors. The old rule is
disabled. Creating two active rules matching one layout blocks guidance until
you disable/replace one. Disabled rules stay in the library for review.

`--library-root` on the teaching command and `--guidance-root` on the reader
can point to the same alternative library folder. Existing reader reviews and
API caches are never rewritten by library management. The installer updates
only known unmodified V3 files, backs them up, and refuses unknown local edits.

Automated tests exercise rule matching and provider request contracts with a
fake transport. They do not measure real Groq/Gemini accuracy. This feature
does not establish 95% accuracy or approval for automatic production imports.
