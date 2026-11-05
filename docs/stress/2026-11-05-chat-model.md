# Chat model stress run - 2026-11-05

This run checked the one-chat general task against the owner's rulings of 2026-11-05, including the new idle shutdown
(ef9ec7b58). Each scenario ran alone in a throwaway TASKUARY_HOME, on the real claude CLI, through the real server. Every
send was stubbed, so nothing left the machine. The people are invented (Ray Colton at `northwind.example`). The
screenshots and the driver stay local in `docs/stress/shots`, `docs/stress/runs` and `docs/stress/logs`, and none of them
is committed.

## Scenarios

| # | scenario | channel | result | shot |
|---|---|---|---|---|
| 1 | The agent answers. The owner types a correction, the line shows at once, the old draft becomes history and the new turn brings a new draft. | email | Passed. The line showed in under 2 s and the correction turn drafted the reply. On the first try the page crashed (defect 1). The read-only history draft was also seen in scenarios 4 and 5. | email-01-s1-final |
| 2 | Two mails arrive while the agent works. | WhatsApp | Passed. Each mail showed on the right, above the turn it woke. The two woke two turns, not one, because the first arrived after the typed turn ended. On the first try triage made one of the mails a new task, as ruled (a new ask is a new task). The page crashed on one run (defect 1). | whatsapp-01-s2-final, s2a-whatsapp-final |
| 3 | The owner answers the thread themselves. | email | The agent re-thought and did not close the task. The line saying it saw the owner's reply, and its "ready for Mark done", were only in its words, which the chat hides (defect 3, fixed). | email-01-s3-final |
| 4 | Idle shutdown with the period cut to 25 s. Then a typed line, then a joined mail. | email | Passed. The agent idled out twice and came back as the same run each time, on the same CLI conversation. The chat read as one conversation and nothing was added to it. On one run the page crashed right after the typed line (defect 1). The idle state read "agent stopped" (defect 2) and the page chrome changed (defect 6). | email-01-s4-idle, email-01-s4-final |
| 5 | A closed task, typed on. | email | Passed. The task reopened (in_progress) and carried on, and the line showed in 1.8 s. A "Continuing from the saved conversation." banner sat over the chat (defect 4). | email-01-s5-final |

## Defects

| # | where | expected | saw | status |
|---|---|---|---|---|
| 1 | task page, right after the owner types while a draft card is up | the chat keeps drawing | "Something in this view failed to draw" with "Maximum update depth exceeded" in 3 of 8 runs. The draft card is mounted twice for a moment, under the old turn and the new one. Each copy re-registered the same row verbs on every render and they took the ids back and forth (actionRow.put). | fixed c22464bea (node test pins it). Not seen again in the 3 runs after. |
| 2 | header and rail, after an idle-out with no draft | the task as it is | "agent stopped" in the header, and "the assistant's conversation from Nov 5 is saved" on the rail (funnel.paused_conversation) | fixed 5605bf48d |
| 3 | the re-think after the owner answered the thread | "I see you answered Ray there", then the recommendation | that line was in the turn's words only. A chat task draws the summary in their place. | fixed cf58fa5ff: the re-plan asks for the line at the start of the summary's "did" too |
| 4 | a closed chat task typed on with no CLI conversation to resume | no banners | "Continuing from the saved conversation." over the chat | fixed c22464bea |
| 5 | the stamp of a turn still running | the time only | "TASKUARY · 2:25 PM · ran 0s" over "Working on this…" | fixed c22464bea |
| 6 | the task page when no agent session is up (an idle-out, and as before a restart) | the chat UI unchanged | the page uses the no-session layout: the Came from column, a row of Mark done / Hand it to a person / Attach a file / Close with a note / Share, and Remind me / Watch it / Not a task / Change. The chat itself and its box are unchanged. With a live session the page shows only Mark done. | ASK OWNER (layout) |
| 7 | the read-only draft under an earlier turn | what that turn drafted | the draft as it reads now. A turn keeps the draft's ID, not its words, and the agent rewrites one review in place, so an earlier turn's card shows a later turn's text ("sorry this is past your Wednesday cut-off" under the turn before Ray moved his deadline). One draft can appear 2-3 times down the chat. | ASK OWNER |
| 8 | the header while the agent is parked over a ready reply | "ready to send" (the Board's own rule, taskstate) | "agent waiting on you" while the session is live. It reads "ready to send" once the agent idles out. | open, minor |
| 9 | an agent's question plus its Next steps | the question said once | "For you to do: give me the date…" and, under it, the same question as the agent's ask (scenarios 2 and 4) | open (agent wording, seen before as defect 13 of the agent-chat run) |
| 10 | the owner's own reply on the thread | - | it draws nothing in the chat, as ruled ("not bubbles"). The re-think under it says what it saw (now in the summary, defect 3). | as designed |

## How to run it again

Run `STRESS_SCEN=<1-5> python docs/stress/driver.py <email|whatsapp> 1` with the driver's `flow_idle.py`. Each scenario
takes 1-4 minutes. Scenario 4 cuts `clipool.IDLE_SECONDS` to 25 s. `docs/stress/replay.py <home> <tid> <png>` serves a
finished home again and shoots one task page. `REPLAY_LIVE=1` adds a live session, and `REPLAY_STUB=<s>` with
`REPLAY_DRAFT=1` adds a stub turn that drafts partway through.
