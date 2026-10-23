// THE ASSISTANT LIGHTS THE ROW'S OWN BUTTON (the owner, 2026-10-19: "the assistant again should just be a router to actions or answer quick
// questions ... it brings up tasks/settings/action buttons" and "it should just surface the correct button"). A typed ask that means an act
// comes back with `light` (concierge._lit): the item it names is brought up the rail's road, and the row's real verb for the act is filled -
// the Advisor's tint, never a button of its own - until the owner presses something or the table moves on. Pure, so test/assistantLight.test.mjs
// can hold it.

// the server's `light` as the page keeps it; `landed` turns true once its item is the one on the table. `line` is what the strip says over it -
// nothing since 2026-10-23 (the owner: "buttons do the talking", "I hate free text"): "Press Mark done when you're sure." is gone, the
// filled button is the whole of it
export const lightOf = (light) => (light && (light.verb || light.key)
  ? { verb: light.verb || "", label: light.label || "", line: light.line || "", key: light.key || "",
      tid: light.tid ? Number(light.tid) : null, landed: false } : null);
// is the lit item the one on the table - by its key, or by its task (a task brought up by name lands as its mail's row)
export const litOn = (lit, table) => !!lit && !!table?.key && (lit.key === table.key || (!!lit.tid && Number(table.tid) === lit.tid));
// the pick the row fills: the Assistant's, while its item is on the table - it outranks the Advisor's, which would fill another button
export const litPick = (lit, table) => (litOn(lit, table) && lit.verb ? { verb: lit.verb, label: lit.label, line: lit.line || "" } : null);
// the light after the table moved: it lands on its item, and once landed any other item puts it out
export const litAfter = (lit, table) => (!lit ? null : litOn(lit, table) ? (lit.landed ? lit : { ...lit, landed: true }) : lit.landed ? null : lit);
// ...and where its item is not on the table yet, the key to bring up (null: it is up already, or names none)
export const litPull = (lit, table) => (lit?.key && !litOn(lit, table) ? lit.key : null);
