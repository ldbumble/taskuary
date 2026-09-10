# Act on a market report through Robinhood
when:      a scheduled market or portfolio report lands with something worth acting on; the owner asks what a report means for the portfolio; a holding moves enough to be worth a look
uses:      robinhood (read: portfolio, positions, orders; orders are PROPOSED, never placed) · yahoo · finnhub · polygon · alpaca
steps:     run robinhood_tools first and use only the names it prints → read the CURRENT positions,
           balances and open orders before saying anything about what to do → re-check the price
           yourself at the moment you write the proposal, because the report's number is already
           stale → propose ONE order with the quote you saw, the size, and the reasoning that
           justifies it → say plainly what would make it the wrong trade
alone:     reading. Positions, balances, order history, transactions, watchlists, quotes, and writing up what the report means.
ask first: EVERY order, without exception - propose it and stop. Also ask before proposing at all when the analysis rests on one source, when the position would be more than the owner has sized before, when the market is closed, or when the report itself flagged its data as partial or capped.
done when: the proposal is in Review carrying the tool, the symbol, the side, the size, the price you actually saw and the reasoning - or the owner approved it and Robinhood's confirmation is on the task

<!-- WHY THIS PLAYBOOK IS SHAPED LIKE THIS

The Robinhood card ships at authority READ, so `robinhood_order` cannot run for an agent at all:
it becomes a proposal the owner approves in Review. This playbook does not soften that, and it
should not be edited to. An agent here reads untrusted email upstream of a live brokerage
account, and the approval click is the thing standing between those two facts.

THE TOOL NAMES ARE NOT DOCUMENTED. Robinhood publishes capabilities, not a manifest, and the
names differ by account - so `robinhood_tools` is the first step of every job, not an optional
discovery. A guessed tool name is a failed run at best.

ORDERS REACH ONLY THE AGENTIC ACCOUNT. That is Robinhood's own boundary: a separate account the
owner funds deliberately. Never write as though the whole portfolio were reachable, and never
propose a size the agentic account cannot cover - read the balance first.

RE-QUOTE AT PROPOSAL TIME. A report is a snapshot from whenever it ran; an approval happens
whenever the owner next opens Review. A proposal carrying the report's stale price asks the
owner to approve a number that no longer exists. Fetch the price as you write it, and say when
you fetched it.

SAY WHAT WOULD MAKE IT WRONG. A trade the owner cannot check is a trade they should refuse. One
line naming the assumption that would sink it is worth more than a paragraph of confidence. -->
