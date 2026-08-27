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
