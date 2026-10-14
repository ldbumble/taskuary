# Report a bug from where it happened

Status: design, 2026-10-14. Approved in conversation; this is the written spec.

## Why

When Taskuary hits an error, the person who saw it has the context and the bug tracker needs it, but today the
only road is the Help icon in the top bar, which opens GitHub's empty "new issue" chooser
(`TaskHubPage.SUPPORT_URL`). The person has to remember what happened, find the version, find the log, and write it
up. Most don't.

The owner's ask: any error the system meets gets a button on the Assistant that files the bug; one popup, already
filled in, and Send. It is the Help button, made automatic for errors.

## Decisions made in conversation

- **Technical only, previewed.** The tracker (`ldbumble/taskuary`) is public. A report carries the error, where it
  happened, versions and the relevant log lines - scrubbed - and never mail, names, task text or a screenshot by
  default. The popup shows exactly what will be sent.
- **The help-button road.** Most users have no GitHub API connection. Send opens GitHub's new-issue page with the
  title and body filled in; the person presses Submit there. No token is used.

## Success criteria

1. Every error the Assistant shows, and every failing item under the bell, offers **Report this bug**.
2. The popup is filled before it opens: a title, two or three sentences of what happened and what was expected, and
   a collapsed technical section. The person can edit all of it.
3. Planted private data - addresses, names, task titles, message text, repository names, user-folder paths - never
   survives into the text that leaves.
4. Send opens a GitHub new-issue URL that stays under GitHub's length limit; anything longer is offered as
   **Copy full report** for pasting.
5. The Help icon opens the same popup with no error attached.

## 1. Where the button appears

- **Assistant errors.** Any Assistant message that reports a failure - a failed API call, a crash caught by the page,
  an agent or report run that failed, a triage error - carries one quiet link under it: **Report this bug**. Not on
  ordinary messages.
- **The bell.** Each failing item in the bell's list (`problems`) gets the same link beside its existing "fix it" road.
- **The Help icon** in the top bar opens the popup empty of an error ("Something is wrong").
- **Page crashes.** An error boundary around the app and a `window.onerror` / `unhandledrejection` handler record the
  last client error, so a crash that leaves no Assistant message still has a report ready from the Help icon.

## 2. What is collected - by code, no model

`taskuary/bugreport.py`, `collect(store, ref) -> dict`, where `ref` names the error (a problem id, a run id, a client
error id, or nothing):

- the error text, its type, and where: the screen, the API route or the job/run kind;
- Taskuary version (`taskuary.__version__`), install kind (exe / pip / docker / editable), OS and version, Python
  version;
- the AI brains in use - CLI names and connector types only - and which connector types are switched on;
- the last ~30 lines of `~/.taskuary/taskuary.log` around the error's time;
- the last few owner actions as action names from the UI ("pressed Start on a coding task"), never titles or text.

The client sends its part (screen, client error and stack, recent action names) to `POST /api/bug-report/draft`; the
server adds its part and returns the draft.

## 3. Scrubbing

`bugreport.scrub(text, store) -> str`, applied to everything before the person sees it:

1. `redact.scrub` (credentials), as every prompt door already does.
2. Then, replacing each hit with `[removed]`:
   - email addresses, and URLs other than Taskuary's own docs and GitHub repo;
   - the text of any task title, task summary or message subject/body present in the store that appears in the
     report (exact substring match against the store, longest first);
   - names from the owner's contacts and connected accounts (senders and recipients known to the store,
     connector account names);
   - repository names other than `ldbumble/taskuary`, and checkout paths;
   - paths under the user's folder: `C:\Users\<name>\...` and `/home/<name>/...`, `/Users/<name>/...` become `~\...`;
   - hostnames and IP addresses other than localhost.

The scrub fails closed: if it raises, the draft is refused with "could not prepare a safe report - copy the error
yourself", never sent unscrubbed.

## 4. The explanation

The Assistant's brain (the light gear, as triage uses) writes the title and two or three sentences - what the person
was doing, what happened, what was expected - **from the scrubbed facts only**. It never sees mail or tasks, so it
cannot put them in; its output is scrubbed again. With no brain, the title is the error's first line and the
explanation is left for the person.

## 5. The popup

- Shows: the title (editable), the explanation (editable), and a collapsed **Technical details** section (editable)
  with the facts from section 2 after scrubbing.
- **Add a screenshot** - off by default. When ticked it captures the Taskuary window with every text block blurred
  (the page renders its own snapshot with text replaced by grey bars); the image is put on the clipboard, because a
  GitHub URL cannot carry an image, and the issue body says "paste the screenshot here".
- **Send** opens `https://github.com/ldbumble/taskuary/issues/new?title=...&body=...&labels=bug` in the browser.
  If the encoded URL would pass ~7,500 characters, the technical section is cut to fit and **Copy full report** puts
  the whole text on the clipboard, with a line in the body saying the full report was copied to paste.
- The popup says plainly: "This goes to a public GitHub page. Check it before you submit."

## 6. The report on GitHub

Body template:

```
### What happened
<explanation>

### Where
<screen / route / job>

### Error
<error text and type, scrubbed>

### Environment
Taskuary <version> (<install kind>) · <OS> · Python <x.y> · brains: <names> · connectors: <types>

<details><summary>Log lines</summary>

<scrubbed log excerpt>
</details>
```

Labels: `bug`. A fingerprint line (`fingerprint: <hash of error type + route/job + first frame>`) lets the maintainer
spot repeats; nothing deduplicates automatically.

## Not in this design

Filing through the API with a token, automatic duplicate detection, attaching files, and reports for problems
that raised no error ("it is slow") beyond the Help icon's free text.

## Testing

- **Scrub:** a store seeded with invented people, addresses, task titles, message bodies, repos and user-folder
  paths; a report built from an error whose text and log lines contain all of them; assert none survive and
  `[removed]` stands in their place. Fails closed when scrub raises.
- **Collect:** each error source (problem, run, client error, none) yields the expected facts; log lines are
  windowed to the error time.
- **URL:** under the limit for a long log; the cut keeps title and explanation intact; `labels=bug` present.
- **UI:** the link appears on an error message and a bell item and not on an ordinary message; the popup shows exactly
  the text that the URL carries; Send builds that URL; Help opens the popup with no error.
- **Brain:** the explanation prompt contains only scrubbed facts (assert no seeded private string reaches the model).
