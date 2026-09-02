import test from "node:test";
import assert from "node:assert/strict";
import { feedHeaders, feedOk, takeFeed, threadDetail } from "../src/feedLoad.js";

test("a first load sends no If-None-Match", () => {
  assert.deepEqual(feedHeaders(""), {});
  assert.deepEqual(feedHeaders('"1-2-3"'), { "If-None-Match": '"1-2-3"' });
});

test("304 keeps the list and does not clobber the etag", () => {
  const etag = { current: '"old"' };
  assert.equal(takeFeed({ status: 304, headers: { etag: '"new"' }, data: { data: [] } }, etag), null);
  assert.equal(etag.current, '"old"');
});

test("200 replaces the list and stores the etag, case-insensitive header", () => {
  const etag = { current: "" };
  const rows = takeFeed({ status: 200, headers: { ETag: '"abc"' }, data: { data: [{ MessageId: 1 }] } }, etag);
  assert.equal(rows.length, 1);
  assert.equal(etag.current, '"abc"');
});

test("axios must treat 304 as success or it would throw and dim the Timeline", () => {
  assert.equal(feedOk(200), true);
  assert.equal(feedOk(304), true);
  assert.equal(feedOk(500), false);
});

test("a taskless FYI reopens with its persisted reply draft", () => {
  const review = { ReviewId: 9, Status: "pending", DraftText: "Feel better." };
  assert.deepEqual(threadDetail({ messages: [{ MessageId: 3 }], reviews: [review] }), {
    messages: [{ MessageId: 3 }], routes: [], reviews: [review],
  });
});
