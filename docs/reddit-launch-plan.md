# Reddit launch plan

Research checked on 2026-08-30. Reddit community rules and pinned threads change often, so
open the live rules and the current pinned thread again immediately before posting. This is
a review document only; it does not authorize posting.

## Recommendation

Use four tailored posts, one at a time:

1. **r/opensource — standalone post with `Promotional` flair.** Best combination of audience
   fit and main-feed visibility. Taskuary is MIT-licensed and has a public repository,
   documentation, releases, and contribution guidance. The community permits limited
   self-promotion but rejects drive-by posting; the author must disclose the relationship,
   use the correct flair, participate in the comments, and meet an undisclosed karma gate.
2. **r/selfhosted — top-level comment in the current New Project Megathread.** Best end-user
   fit and the safest immediate venue. Taskuary's first public commit is 2026-08-17, so it is
   younger than three months and a standalone post is currently prohibited. The weekly
   thread explicitly asks for project, link, problem/features, deployment, and AI-involvement
   details. It allows comments any day, even though a new thread appears each Friday.
3. **r/ChatGPTCoding — comment in the weekly self-promotion thread.** Strong fit for people
   already using Codex, Claude Code, Cursor, Gemini, or Copilot. The thread asks what was
   built, the problem, models/tools, intended user, requested feedback, and affiliation.
   Promotional standalone posts are removed.
4. **r/codex — comment in the next weekly Showcase thread.** Strong fit because Taskuary can
   turn incoming work into live Codex sessions and Codex has been part of its development
   workflow. The current contest window has already closed; use the next thread and describe
   the Codex-specific workflow rather than posting a generic product pitch.

Post to **r/SideProject** later as a secondary discovery channel. It welcomes projects in the
main feed, but it is crowded with launch posts and recent community discussion is openly
hostile to link-dropping. A candid build story and one specific feedback question are more
appropriate there than a feature list.

Use these only as low-priority, thread-only placements:

- **r/devops:** the pinned weekly self-promotion thread only. Focus on GitHub/GitLab/Jira,
  Sentry/PagerDuty, review gates, audit evidence, and self-hosting.
- **r/github:** the pinned self-promotion megathread only. Keep it to a short description,
  repository link, stack, and contribution request.
- **r/coolgithubprojects:** reasonable topical fit, but weak average discussion and no clear,
  dependable self-promotion rule surfaced. Ask moderators before using it rather than assuming
  that surviving project posts establish permission.

Do not post to these now:

- **r/productivity:** promotion, advertising, surveys, and solicitation are prohibited.
- **r/github main feed:** project promotion is redirected to its pinned megathread.
- **r/devops main feed:** project and vendor promotion is redirected to its weekly thread.
- **r/selfhosted main feed:** projects under three months old are redirected to the New Project
  Megathread. Taskuary becomes eligible on 2026-11-17, assuming the rules do not change.
- **r/homelab:** software showcases require at least one month of public commit history,
  screenshots, subreddit karma, the correct AI-use flair, and a written AI disclosure.
  Taskuary is not age-eligible until 2026-09-17. Reassess relevance and the author's subreddit
  karma then.
- **r/LocalLLaMA:** limited promotion is subject to roughly a 1-in-10 participation guideline
  and disclosure. Ollama support alone is not enough for a launch post; use this community
  only after producing a substantive local-model benchmark or implementation write-up.
- **r/SaaS:** promotion is rate-limited and the audience is a poor match for a free,
  self-hosted application. Do not spend the account's limited promotional allowance here.
- **r/automation, r/artificial, r/startups, r/Entrepreneur, and r/marketing:** promotion is
  prohibited, tightly conditional, or a weak audience match. Do not disguise a launch as a
  discussion post.

## Posting safeguards

- Post from Uri's established personal account, not a new brand account. Do not farm karma.
- Before each post, read the live rules, pinned posts, and the submission form. If the account
  does not meet a karma gate, participate normally and wait; do not try another flair.
- Say **"I maintain/built Taskuary"** near the start. Never present it as something merely
  discovered.
- Do not reuse identical text or post to several communities on the same day. Space posts by
  at least a few days, tailor each one, and respond to every substantive comment.
- Avoid vote requests, awards, referral links, unsolicited DMs, affiliate links, or asking
  friends/alternate accounts to boost a post.
- Be precise about privacy. Taskuary stores its own state locally, but connected mail/chat
  services and a configured cloud AI provider still receive network traffic. Ollama is the
  local-model option. Do not claim that the entire system is offline.
- Be precise about maturity. Say **v0.3.1, early, used daily, and subject to breaking changes
  before 1.0**. Do not call it production-ready or battle-tested.
- Be precise about Docker. The Docker deployment provides the web application; coding CLIs
  and the optional WhatsApp bridge remain host programs.
- Use one direct GitHub link (`https://github.com/ldbumble/taskuary`), not a tracking URL or
  link shortener. Let the README supply screenshots, install options, and deeper detail.
- Stay available after posting. Permission to self-promote is not permission to post and leave.
- If a moderator removes a post, do not repost it under a different title or flair. Read the
  reason and use modmail once, politely, if clarification is genuinely needed.

Reddit's site-wide spam guidance prohibits mass-posting repetitive content and advises people
whose contributions mainly link to something they benefit from to reduce posting frequency.
There is no universal site-wide 90/10 law, although individual communities may use a 10%
participation rule.

## Draft 1 — r/opensource

**Format:** standalone text post

**Flair:** `Promotional`

**Title:** `Taskuary: an MIT-licensed, local-first inbox that hands real work to coding agents`

> Disclosure: I maintain Taskuary.
>
> I built it because the work that should reach a coding agent rarely starts as a clean prompt.
> It arrives in email, Slack or Teams, a GitHub issue, Jira, Sentry, or a scheduled report, and
> somebody still has to decide whether it is real work, a reply, or just FYI.
>
> Taskuary puts those inputs on one local timeline. AI triage classifies each item; repository
> work can open a live Codex, Claude Code, Gemini, Cursor, or Copilot CLI session with the task
> context and the repository's working rules. The owner watches the terminal and reviews the
> evidence and diff. Replies, pushes, comments, and other outbound actions wait for explicit
> approval.
>
> It is Python/React, stores its state in local SQLite, supports Docker and local Ollama as well
> as cloud model providers, and is MIT-licensed. The current release is v0.3.1. It is early and
> breaking changes are still possible before 1.0, but the core funnel and review workflow are
> in daily use.
>
> Repository: https://github.com/ldbumble/taskuary
>
> I would especially value review of the approval boundary and connector architecture. What
> would you require before trusting a tool like this with inbound work, even if every outbound
> action remains human-approved? Contributions, deployment reports, and blunt bug reports are
> welcome.

Why this fits: it identifies the maintainer, states the OSI-approved license, explains the
architecture and maturity, asks for meaningful open-source feedback, and avoids a sales CTA.

## Draft 2 — r/selfhosted New Project Megathread

**Format:** top-level comment in the current pinned New Project Megathread; no standalone post

> **Project Name:** Taskuary
>
> **Repo/Website Link:** https://github.com/ldbumble/taskuary
>
> **Description:** Taskuary is a free, MIT-licensed work hub that runs locally. It brings mail,
> chat, GitHub/GitLab issues, work trackers, alerts, and scheduled reports onto one timeline.
> AI triage separates actionable work from replies and FYI items. Repository tasks can open a
> live coding-agent terminal, while replies, pushes, comments, and other outbound actions wait
> for the owner to approve them.
>
> The data store is local SQLite. A local Ollama or OpenAI-compatible model can handle triage;
> cloud providers are optional. Connected services still require network access, so this is
> local-first rather than fully offline. It is currently v0.3.1, early, used daily, and may
> have breaking changes before 1.0.
>
> **Deployment:** `git clone https://github.com/ldbumble/taskuary`, then `docker compose up`,
> and open `http://127.0.0.1:7787`. The README also documents `pip install taskuary` and a
> Windows executable. Docker runs the web app; coding CLIs and the optional WhatsApp bridge
> stay on the host. The compose setup binds to localhost by default, and the docs explain the
> token required before exposing it to a LAN.
>
> **AI involvement:** Coding agents, including Codex, are part of the development workflow.
> They work in the repository under human direction and review; changes, pushes, and releases
> are not approved automatically.
>
> I maintain the project. I would value deployment feedback, especially around backups,
> upgrades, reverse-proxy expectations, and which connector would make this useful in a real
> self-hosted setup.

## Draft 3 — r/ChatGPTCoding weekly self-promotion thread

**Format:** comment in the current weekly thread; no standalone launch post

> Disclosure: I maintain Taskuary, an MIT-licensed local work hub for people already using AI
> coding CLIs.
>
> The problem it solves is the handoff before coding starts. Work arrives as an email, chat,
> GitHub issue, Jira item, alert, or report; Taskuary triages it, creates a repository-scoped
> task with the relevant context and owner rules, and opens a live Codex, Claude Code, Gemini,
> Cursor, or Copilot session. The human can watch the terminal, answer questions, review the
> diff and test evidence, and approve what happens next. Nothing sends or pushes automatically.
>
> Triage can use Anthropic, OpenAI, Azure OpenAI, OpenRouter, Ollama, or a configured coding
> CLI. The app stores its own state locally, can run with Docker or Python, and is currently
> v0.3.1, so it is useful but still early.
>
> Repo: https://github.com/ldbumble/taskuary
>
> It is for people whose coding-agent workflow starts outside the IDE. I am looking for one
> specific kind of feedback: what context should an inbox-to-agent handoff include by default,
> and what information should it deliberately keep out?

## Draft 4 — r/codex weekly Showcase

**Format:** comment in the next weekly Showcase, not the expired current contest window

> I maintain Taskuary, and Codex is both part of its development workflow and one of the agents
> it can run.
>
> Taskuary takes work that arrives outside the terminal—email, chat, GitHub issues, Jira,
> alerts, or reports—and turns it into a repository-scoped Codex session. It supplies the task
> context and repository rules, streams the live PTY so I can intervene, records the work
> evidence, and stops at the approval boundary. Codex can edit and test locally, but Taskuary
> does not let it push, comment, send, or release without human approval.
>
> The project is MIT-licensed, local-first, and currently v0.3.1:
> https://github.com/ldbumble/taskuary
>
> The hardest design problem has not been starting Codex; it has been deciding what context to
> send, preserving the transcript and evidence, and making the handoff back to a human clear.
> I would be interested in how other Codex users draw that boundary, especially when several
> repositories or sessions are active at once.

## Draft 5 — r/SideProject

**Format:** standalone text post with the most appropriate `Open Source`, `Feedback Wanted`,
or equivalent flair available in the composer

**Title:** `I built a local inbox that decides whether a message needs me, a reply, or a coding agent`

> I kept running into the same gap: coding agents can do substantial repository work, but most
> real work does not arrive as a clean coding prompt. It arrives mixed into email, chat, issues,
> alerts, and reports, and I was still the person copying context between all of them.
>
> I built Taskuary to be that handoff layer. It puts the inputs on one local timeline, uses AI
> to separate tasks from replies and FYI noise, and can open the real task in Codex, Claude
> Code, Gemini, Cursor, or Copilot. I can watch the session and review the result; sending,
> pushing, commenting, and releasing stay behind explicit approval.
>
> It is free and MIT-licensed. The current v0.3.1 release runs through Docker, Python, or a
> Windows executable. It is early and I expect rough edges.
>
> https://github.com/ldbumble/taskuary
>
> I am the maintainer. The feedback I need most is on the first five minutes: does the README
> make it clear who this is for and why it is different from a task manager or an agent UI? If
> not, where does the explanation lose you?

## Optional thread-only drafts

### r/devops weekly self-promotion thread

> Disclosure: I maintain Taskuary, a free MIT-licensed, self-hosted work funnel. It can ingest
> GitHub/GitLab issues, Jira work, Sentry/PagerDuty events, mail, chat, and scheduled reports;
> triage what is actionable; and hand repository work to a live Codex, Claude Code, Gemini,
> Cursor, or Copilot session. Outbound actions remain review-gated, and the review records the
> diff, tests, attempts, and missing evidence.
>
> Docker/Python/Windows release: https://github.com/ldbumble/taskuary
>
> It is v0.3.1 and still early. I would value an operator's view on whether a unified queue like
> this reduces handoff loss or merely creates another alert sink, and what audit or deployment
> controls would be non-negotiable.

### r/github pinned self-promotion megathread

> **Taskuary** is an MIT-licensed, local-first work hub. It unifies inbound mail, chat, issues,
> alerts, and reports; triages them into task/reply/FYI; and can open repository tasks in live
> coding-agent sessions while keeping outbound actions behind human approval.
>
> Repo: https://github.com/ldbumble/taskuary
>
> Stack: Python, FastAPI, React, SQLite; Docker, pip, and Windows builds are available.
>
> Feedback and contributions are especially welcome around connectors, Linux/macOS testing,
> safe approval boundaries, and deployment documentation.

## Source checks

- [Reddit spam guidance](https://support.reddithelp.com/hc/en-us/articles/360043504051-Spam)
- [r/opensource rules](https://www.reddit.com/r/opensource/about/rules) and a
  [current AutoModerator example of its karma gate](https://www.reddit.com/r/opensource/comments/1g4p832/removed/)
- [r/selfhosted rules](https://www.reddit.com/r/selfhosted/about/rules) and the
  [2026-08-27 New Project Megathread](https://www.reddit.com/r/selfhosted/comments/1w07yna/new_project_megathread_week_of_27_aug_2026/)
- [r/ChatGPTCoding weekly thread](https://www.reddit.com/r/ChatGPTCoding/comments/1vwwbap/weekly_self_promotion_thread/)
- [r/codex weekly Showcase](https://www.reddit.com/r/codex/comments/1vyerip/show_rcodex_what_youve_been_building_with_codex/)
- [r/SideProject rules](https://www.reddit.com/r/SideProject/about/rules)
- [r/devops weekly thread](https://www.reddit.com/r/devops/comments/1vwuvha/weekly_self_promotion_thread/)
- [r/github self-promotion megathread](https://www.reddit.com/r/github/comments/1jy8rea/promote_your_projects_here_selfpromotion/)
- [r/homelab software-project rule announcement](https://www.reddit.com/r/homelab/comments/1ty58af/announcement_new_rules_processes_on_software/)
- [r/LocalLLaMA rules](https://www.reddit.com/r/LocalLLaMA/about/rules)
- [r/productivity rules](https://www.reddit.com/r/productivity/about/rules)
- [r/SaaS moderator announcement limiting self-promotion](https://www.reddit.com/r/SaaS/comments/1slno92/new_rule_against_selfpromo/)
