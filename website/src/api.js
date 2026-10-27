// One axios instance for the whole UI; the local server
// needs no auth (localhost) - if [server].token is set, put it in localStorage.
import axios from "axios";
import demoApi, { DEMO } from "./demoApi.js";
import { keepDetail } from "./apiError.js";
import { staleToken, UNLINKED_EVENT } from "./unlinked.js";
import { record, recordAction } from "./lastError.js";
import { isWrite, noteWrite } from "./wrote.js";
const api = axios.create({ baseURL: "" });
api.interceptors.request.use((c) => {
  const t = localStorage.getItem("taskuary_token");
  if (t) c.headers["X-Taskuary-Token"] = t;
  recordAction(c.method, c.url);         // the shape of each write, for "Report this bug" (lastError.js)
  return c;
});
// A string to render, and the structure to act on, both kept - see apiError.js for why one
// without the other put a red banner over a refusal the app already knew how to absorb.
// Any write, answered or refused, may have changed what the sync caption shows (wrote.js).
const wrote = c => { if (isWrite(c)) noteWrite(); };
api.interceptors.response.use((r) => { wrote(r.config); return r; }, (e) => {
  wrote(e?.config);
  if (staleToken(e, localStorage)) window.dispatchEvent(new Event(UNLINKED_EVENT));
  record(e);
  return Promise.reject(keepDetail(e));
});
// taskuary.com/demo is this same bundle with no server behind it: every call is answered from
// a recording of a real --demo instance instead (demoApi.js). One swap, here, so no component
// has to know which it is talking to.
export default DEMO ? demoApi : api;
