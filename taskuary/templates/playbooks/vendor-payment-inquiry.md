# Answer a vendor's question about an invoice or a payment
when:      a vendor asks whether we received their invoice, when it will be paid, or why it is late; a statement of account or a past-due notice; a "please confirm payment" mail
uses:      intacct (read: vendors, bills, payments)
steps:     find the vendor by the sender's domain and remit-to name (VENDOR) → find each invoice
           they name (APBILL by RECORDID, then by amount and date) → for a paid one, find the
           payment (APPYMT / APBILLPAYMENT) and its date, method and reference → draft one short
           reply giving each invoice's state: paid (date, amount, reference), approved and due
           (due date), in approval, or not found (ask for a copy)
alone:     every lookup, and the drafted reply - the owner approves the reply before it goes
ask first: a vendor asking to change bank or remittance details (never confirm it, flag it for a call-back) · promising a payment date not already on a payment run · a vendor the ledger does not have · an amount that differs from ours
done when: the reply is drafted on the task with each invoice's state, and the ledger record ids it came from are in the task notes

<!-- WHY THIS PLAYBOOK IS SHAPED LIKE THIS

It is read-only on purpose. A payment question never needs a write: the answer is in the ledger,
and the reply is a draft the owner sends. Keeping writes out of this job keeps a stranger's email
away from the ledger's write path.

INVOICE NUMBERS RARELY MATCH EXACTLY. The vendor's "INV-004471" is our "4471". Search by the
digits, then by vendor + amount + date, before calling it missing.

THE BANK-DETAILS RULE IS THE ONE THAT MATTERS. Vendor email compromise is mostly "we changed
banks, please update". It belongs in ask first, never in alone, and the reply must not say
"updated". -->
