The assistant you talk to in the app is reachable from your phone over WhatsApp or Telegram. It is
the same conversation and the same assistant — not a notification feed and not a second, weaker
bot. It can walk you through your work, answer questions about it, and carry out the things the
page can carry out.

## The doorways

A doorway is one chat, on one channel, that the assistant is allowed to speak in. Set it up in
**Settings → Assistant on your phone**, which lists every channel you have connected and lets you
pick the chat and whether it may listen.

1. Connect WhatsApp or Telegram under [Connections](connections#chat).
2. Send a message to the private chat you want to use — on WhatsApp that is the **Message
   yourself** chat.
3. Pick that chat in Settings. Taskuary adds the notification role, names the chat, and switches
   on the assistant for it.

:::rule Only chats you are alone in
The picker offers nothing but chats with one member: you. Groups cannot be selected, because an
answer may name anything in your workspace. The rule is enforced again when a message arrives, so
the picker is a convenience rather than the guard.
:::

Only messages sent by the linked owner account, in that exact chat, are accepted. Taskuary marks
its own bridge output so its notifications can never loop back in as if you had typed them.

## What it can do

Ask it in plain words. These are real examples, not a command list:

- "what needs me?"
- "walk through important email"
- "what is outstanding?"
- "what did the coding agents finish?"
- "reply to Ruth that the numbers are coming tomorrow"

**Walk through** is the one worth knowing. It is the same turn-by-turn walk the Assistant page
runs: one unresolved item at a time, one question, and it waits for your answer before moving on.
The phone is not given a cut-down version of it — the walk carries out the page's job, including
the actions at the end of each item.

Answers you give on the phone land in the desktop conversation too, because it is one
conversation with two doors.

### Approving things

A reply drafted for you can be approved from the phone. Tagged answers use `[tq…]` for a task and
`[rv…]` for a Review item, and the plain words `approve`, `reject` and `no reply` work as
shortcuts on the item currently in front of you.

The approval gate itself does not move: approving on your phone is the same deliberate human
action as approving on the page, and nothing goes out without one.

## The morning line

Once a day, the assistant can open with a short line about the day ahead — what slipped, what is
waiting, today's meetings. It is the morning brief's voice, cut to the length of something you
read while walking.

It fires once per day, not once per app start, and it is the same cap the brief itself uses: if
today's line has gone out, reopening the app does not produce another.

## Handing over

When a conversation on the phone reaches something better done at a keyboard — a coding session,
a long document, a report builder — the assistant hands over rather than pretending. The tab it
hands to locks onto that item so you arrive where the conversation left off, and the phone thread
says so plainly instead of going quiet.

The reverse is true too: a walk started on the page can be picked up on the phone, because the
walk's position belongs to the conversation rather than to the surface you started it on.

## What it will not do

- It will not speak in a group chat, or in a chat you did not choose.
- It will not send anything a human has not approved, on any channel.
- It will not change a setting. Settings are changed in the app, deliberately.
- It will not answer someone else in your chat — only the linked owner account is heard.

:::warn WhatsApp is an unofficial bridge
The WhatsApp connector runs a local bridge against an unofficial protocol. It works well, and it
is not a supported WhatsApp product: use a number you can afford to lose. Telegram uses a proper
bot API and has no such caveat.
:::
