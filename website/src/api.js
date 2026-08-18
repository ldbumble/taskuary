// One axios instance for the whole UI; the local server
// needs no auth (localhost) - if [server].token is set, put it in localStorage.
import axios from "axios";
const api = axios.create({ baseURL: "" });
api.interceptors.request.use((c) => {
  const t = localStorage.getItem("taskuary_token");
  if (t) c.headers["X-Taskuary-Token"] = t;
  return c;
});
// FastAPI validation errors put an ARRAY OF OBJECTS in detail - rendering that in JSX
// crashes React (#31) and blanks the whole app. Normalize every detail to a string.
api.interceptors.response.use(null, (e) => {
  const d = e?.response?.data?.detail;
  if (d && typeof d !== "string") {
    e.response.data.detail = Array.isArray(d)
      ? d.map((x) => `${(x.loc || []).join(".")}: ${x.msg || JSON.stringify(x)}`).join(" · ")
      : JSON.stringify(d);
  }
  return Promise.reject(e);
});
export default api;
