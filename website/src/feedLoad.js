// The Timeline's 30s refresh. If-None-Match + 304 means "nothing landed" without
// replacing the list the user is looking at. loadMore (offset pages) does not use this.

export function feedHeaders(etag) {
  return etag ? { "If-None-Match": etag } : {};
}

export function takeFeed(res, etagRef) {
  if (res.status === 304) return null;
  etagRef.current = res.headers?.etag || res.headers?.ETag || "";
  return res.data?.data || [];
}

export const feedOk = (s) => (s >= 200 && s < 300) || s === 304;

// A task carries detail through /tasks/:id; a filed FYI gets the smaller thread contract.
// Reviews are part of that contract: omitting them made a persisted draft disappear only in
// the browser while the Timeline row still (correctly) said "reply ready".
export const threadDetail = (data = {}) => ({
  messages: data.messages || [],
  routes: data.routes || [],
  reviews: data.reviews || [],
});

// A message exists before triage has decided whether to create a task. The detail request still
// has to load in that taskless interval; using TaskId as the loading flag made the panel render
// an incomplete workflow and look blank precisely while the funnel was busiest.
export const detailPhase = (row, detail) => !detail ? "loading"
  : row?.MsgStatus === "triaging" ? "triaging" : "ready";
