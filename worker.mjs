// Cloudflare Workers entry point for taskuary.com. The site is static, but these two API
// endpoints need to run before the static asset layer. The handlers remain shared with Pages so
// a fork can deploy either way without maintaining two versions of the analytics code.
import { onRequestGet as readEvents, onRequestPost as recordEvents } from "./functions/api/ev.js";
import {
  onRequestDelete as signOut,
  onRequestGet as readSession,
  onRequestPost as signIn,
} from "./functions/api/stats-auth.js";

const ROUTES = {
  "/api/ev": { GET: readEvents, POST: recordEvents },
  "/api/stats-auth": { GET: readSession, POST: signIn, DELETE: signOut },
};

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname.replace(/\/$/, "") || "/";
    const route = ROUTES[path];
    if (route) {
      const handler = route[request.method];
      if (handler) return handler({ request, env });
      return new Response("Method not allowed", {
        status: 405,
        headers: { Allow: Object.keys(route).join(", "), "Cache-Control": "no-store" },
      });
    }
    return env.ASSETS.fetch(request);
  },
};
