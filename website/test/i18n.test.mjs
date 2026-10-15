import test from "node:test";
import assert from "node:assert/strict";
import { getLocale, groupLabel, loadLocale, localized, saveLocale, setLocale, t } from "../src/i18n.js";

test("UI text defaults to pt-BR and preserves canonical metadata", async () => {
  setLocale("pt-BR");
  assert.equal(getLocale(), "pt-BR");
  assert.equal(t("Settings"), "Configurações");
  assert.equal(t("{n} settings", { n: 3 }), "3 configurações");
  const knob = { group: "Display", label: "Language", i18n: { "pt-BR": { label: "Idioma" } } };
  assert.equal(localized(knob, "label"), "Idioma");
  assert.equal(groupLabel({ group_labels: { "pt-BR": { Display: "Exibição" } } }, knob.group), "Exibição");
  assert.equal(knob.group, "Display");
  assert.equal(localized({ title: "Outlook mail", i18n: { "pt-BR": { title: "E-mail do Outlook" } } }, "title"), "E-mail do Outlook");
  assert.equal(t("Delete {what}?", { what: "<script>$&{n}</script>" }), "Excluir <script>$&{n}</script>?");
  assert.equal(t("Unknown {key}"), "Unknown {key}");
  assert.equal(t("Unknown {toString}"), "Unknown {toString}");

  const calls = [];
  const api = { get: async () => ({ data: { data: [{ Name: "locale", Value: "en" }] } }), patch: async (...args) => calls.push(args) };
  await loadLocale(api);
  assert.equal(t("Settings"), "Settings");
  await saveLocale(api, "pt-BR");
  assert.deepEqual(calls, [["/api/settings", { name: "locale", value: "pt-BR" }]]);
  await assert.rejects(saveLocale(api, "fr"), TypeError);
});
