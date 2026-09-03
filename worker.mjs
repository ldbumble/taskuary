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
  "/api/stats-auth": { GET: readSession, POST: signIn, DELETE: signOut },
};

class Statement {
  constructor(sql, query) { this.sql = sql; this.query = query; this.args = []; }
  bind(...args) { this.args = args; return this; }
  run() { return this.sql.exec(this.query, ...this.args); }
  async all() { return { results: Array.from(this.run()) }; }
}

// A tiny D1-shaped adapter lets the same audited event handlers run against a built-in,
// SQLite-backed Durable Object. No database id, token, variable, or dashboard binding is needed.
export class StatsStore {
  constructor(ctx) {
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS ev (
      Id INTEGER PRIMARY KEY, At TEXT NOT NULL, Sid TEXT NOT NULL, Kind TEXT NOT NULL,
      What TEXT DEFAULT '', N INTEGER DEFAULT 0, Page TEXT DEFAULT '', Ref TEXT DEFAULT '',
      Country TEXT DEFAULT '', Mobile INTEGER DEFAULT 0
    ); CREATE INDEX IF NOT EXISTS ev_at ON ev(At); CREATE INDEX IF NOT EXISTS ev_sid ON ev(Sid);`);
    this.db = {
      prepare: (query) => new Statement(this.sql, query),
      batch: async (statements) => statements.map((statement) => statement.run()),
    };
  }

  fetch(request) {
    const handler = request.method === "POST" ? recordEvents : request.method === "GET" ? readEvents : null;
    return handler ? handler({ request, env: { DEMO_EVENTS: this.db } })
      : new Response("Method not allowed", { status: 405, headers: { Allow: "GET, POST" } });
  }
}

const analytics = (request, env) => {
  // Keep compatibility with the original D1 deployment when a fork already has that binding.
  if (env.DEMO_EVENTS) {
    const handler = request.method === "POST" ? recordEvents : request.method === "GET" ? readEvents : null;
    return handler ? handler({ request, env })
      : new Response("Method not allowed", { status: 405, headers: { Allow: "GET, POST" } });
  }
  const namespace = env.ANALYTICS_STORE;
  if (!namespace) return (request.method === "POST" ? recordEvents : readEvents)({ request, env });
  return namespace.get(namespace.idFromName("taskuary.com")).fetch(request);
};

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname.replace(/\/$/, "") || "/";
    if (path === "/api/ev") return analytics(request, env);
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
