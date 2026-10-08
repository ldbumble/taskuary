# Review the bills waiting for approval in the bill-approval portal
when:      the owner asks to review or approve the bills waiting in the bill-approval portal; the daily portal-approvals workflow
uses:      intacct (read: vendors, bills, payments - for checking only; the portal posts approved bills to the ledger itself) · browser (the bill-approval portal, signed in by the owner)
steps:     open the portal in the browser (the owner's saved sign-in) → list every bill waiting for the
           owner's approval: vendor, invoice number, invoice date, due date, amount, GL coding, PO, and
           any notes or attachments the portal shows → check each one: the vendor exists and is active
           in the ledger; no bill with the same vendor and invoice number (or the same vendor, amount and
           date) is already in the ledger or elsewhere in the portal; the amount is in line with that
           vendor's recent bills; the GL coding matches how that vendor is usually coded; the dates make
           sense → give each bill a verdict: LOOKS GOOD, or NEEDS A LOOK with the reason → end the turn by
           asking which to approve, offering "approve the N that look good" → approve in the portal
           exactly the bills the owner named, one at a time, re-reading each one's vendor and amount on
           screen first → report what was approved
alone:     reading the portal and the ledger, checking, and writing the table with verdicts
ask first: EVERY approval. Approve only bills the owner named in this conversation after seeing the table, never on your own judgement, never "all" unless they said all · never reject, re-code, edit, split or comment on a bill, and never touch vendor or bank details · if a bill on screen no longer matches the table (amount, vendor), stop and say so instead of approving it
done when: the table of bills with verdicts is on the task, and every bill the owner named is approved in the portal and listed with its vendor, number and amount - or the owner said approve none

<!-- WHY THIS PLAYBOOK IS SHAPED LIKE THIS

The portal posts approved bills to the ledger by itself, so the job is the approval, not the
posting. The ledger is read only to check a bill: does the vendor exist, has this bill already
been entered, is the amount and coding normal for this vendor.

An Approve click in the browser is gated by nothing but these words. That is why the owner's
yes, in the conversation, after seeing the table, is what lets each bill through. Once the
owner trusts the verdicts, a rule can be written in `alone:` (for example "LOOKS GOOD bills
under $500 from vendors with five clean prior bills") - start without one.

RE-READ BEFORE CLICKING. The table may be minutes old when the owner answers. A bill whose amount
or vendor changed in between is not the bill they approved.

Replace "the bill-approval portal" above with your portal's name and address once you know them.
The workflow made with this playbook already carries the address. -->
