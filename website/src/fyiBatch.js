// HOW MANY FYI THIS SCREEN READS TOGETHER (the owner, 2026-10-28: "by default do 6 at a time so it looks combined? though if the screen is
// smaller maybe 4 at a time - based off screen size"). Six fit a desktop's Came from without scrolling; a laptop under 800px tall or a phone
// gets four. Sent on every request (api.js, the two streams) as X-Taskuary-Fyi-Batch, so the server cuts each batch to the screen that asked;
// a number the owner set in Settings -> Assistant still wins (funnel.fyi_batch_size). Read per request: a resized window's next batch follows.
export const FYI_HEADER = "X-Taskuary-Fyi-Batch";
export const fyiBatchFor = (w, h) => (w <= 600 || h < 800 ? 4 : 6);
export const fyiBatch = () => (typeof window === "undefined" ? 4 : fyiBatchFor(window.innerWidth, window.innerHeight));
export const fyiHeaders = () => ({ [FYI_HEADER]: String(fyiBatch()) });
