// AI USED AND "TALK TO THIS AGENT FROM…" ARE THE HEADER'S, NOT THE CHAT'S (the owner, 2026-11-06): never at the bottom of the chat - quiet icon
// buttons in the task's top-right corner beside the status, each opening the same content in a popover; the agent's chats for a coding task only.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("both live in the header's corner, each a popover; neither is mounted at the foot of a chat", () => {
  const page = read("TaskPage.jsx"), head = page.slice(page.indexOf("<StatusPill status={status}"), page.indexOf("{onExpand && ("));
  assert.match(head, /<HeadPop id="ai-used" title="AI used" icon=\{<TokenOutlinedIcon[^>]*\/>\}><AiUsed taskId=\{t\.TaskId\} pop \/><\/HeadPop>/);
  assert.match(head, /\{canCode && t\.Kind === "coding" && <HeadPop id="agent-channels" title="Talk to this agent from…"[\s\S]*<AgentChannels taskId=\{t\.TaskId\} pop \/><\/HeadPop>\}/);
  assert.match(page, /<Popover open=\{!!at\} anchorEl=\{at\}/);
  assert.equal((page.match(/<AiUsed /g) || []).length, 1, "once, in the header");
  for (const f of ["CodingChat.jsx", "GeneralWorkspace.jsx"]) assert.doesNotMatch(read(f), /<AgentChannels |\{tail\}|\btail=\{/, f);
  assert.doesNotMatch(page, /\btail=\{/);
  // ...the same content: open from the start in the popover, its fold only where it is not one
  assert.match(read("AiUsed.jsx"), /const \[open, setOpen\] = useState\(pop\)/);
  assert.match(read("AgentChannels.jsx"), /if \(pop\) return <Box data-tq-agent-channels="pop">/);
});
