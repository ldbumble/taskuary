# Bring approved bills from the bill-approval portal into the ledger
when:      the owner asks to review outstanding bills in the bill-approval portal, or to sync the portal's approved bills to the accounting system; the daily portal-to-ledger workflow
uses:      intacct (read: vendors, bills; bills are PROPOSED, never posted) · browser (the bill-approval portal, signed in by the owner)
steps:     open the portal in the browser (the owner's saved sign-in) → list the bills waiting
           and the bills approved since the last run, reading each one's vendor, invoice number,
           date, due date, amount and GL coding → for every approved bill, look it up in the
           ledger (APBILL by vendor + invoice number) → a bill missing from the ledger becomes ONE
           proposal per bill (run_tool intacct_create, object APBILL, with VENDORID, RECORDID,
           WHENCREATED, WHENDUE and its APBILLITEMS lines) → report the rest as a table: waiting in
           the portal, already in the ledger, amounts that disagree
alone:     reading the portal and the ledger, comparing them, and writing the table
ask first: EVERY bill posted to the ledger (propose it, never post it yourself) · approving, rejecting or coding anything in the portal · a vendor the ledger does not have · any bill whose amount, vendor or coding differs between the two systems
done when: the run's table is on the task (waiting / in the ledger / disagree), and every bill that should be posted is a proposal on the task carrying the full record

<!-- WHY THIS PLAYBOOK IS SHAPED LIKE THIS

Many bill-approval portals have no API, so this job runs in the browser the owner watches. The
owner signs in by hand once, in the pane, and the saved sign-in carries the daily run. When the
portal turns the session away, the run stops on the sign-in page and waits; it never types a
password or a code.

A browser click is not gated by code. Only the instructions keep the agent from pressing Approve.
That is why the portal side of this playbook is read-only: the agent reads and compares, and
every change goes through a ledger proposal the owner approves on the task.

DUPLICATES ARE THE EXPENSIVE MISTAKE. Look up vendor + invoice number before every proposal,
including paid and voided bills. A bill posted twice gets paid twice.

Replace "the bill-approval portal" above with your portal's name and address once you know them.
The workflow made with this playbook already carries the address. -->
