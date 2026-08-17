// Same axios surface the FanApp components were written against; the local server
// needs no auth (localhost) - if [server].token is set, put it in localStorage.
import axios from "axios";
const api = axios.create({ baseURL: "" });
api.interceptors.request.use((c) => {
  const t = localStorage.getItem("taskuary_token");
  if (t) c.headers["X-Taskuary-Token"] = t;
  return c;
});
export default api;
