# Post a card transaction as an AP bill
when:      a transaction or statement line from the card feed; a mail from the card issuer with a statement attached
uses:      quickbooks (write: bills, vendors)  ·  teller (read)
steps:     match the merchant to a vendor (create one only if the owner says so) → pick the
           expense account from the memo and the vendor's history → create the bill dated the
           transaction date, memo = card last-4 + transaction id → attach the receipt if one came in
alone:     bills under $500 to a vendor seen before, in an open period
ask first: a new vendor · anything over $500 · a closed period · a split across accounts
done when: the bill exists in QuickBooks and its DocNumber is on the task

<!-- A playbook is how THIS company does ONE kind of job, written for the agent that will do it.
Keep the six lines above - `when` is what triage matches a new message against, `uses` names the
connections it touches (the card for each shows this playbook), `alone` and `ask first` are the
line between "just do it" and "ask the owner in the session", and `done when` is the receipt.
Anything below them is yours: house rules, examples, the ids and names an agent would otherwise
have to ask for. Delete this playbook if the example does not fit; the first real one is drafted
for you when an agent finishes a kind of job for the first time. -->
