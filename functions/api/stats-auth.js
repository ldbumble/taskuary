import {
  clearStatsCookie, createStatsSession, credentialsMatch, hasStatsSession,
  setStatsCookie, statsCredentials,
} from "../lib/statsAuth.js";

const json = (body, status = 200, headers = {}) => Response.json(body, {
  status, headers: { "Cache-Control": "no-store", ...headers },
});

export async function onRequestGet({ request, env }) {
  const authenticated = await hasStatsSession(request, env);
  return json({ authenticated, username: authenticated ? statsCredentials(env).username : null });
}

export async function onRequestPost({ request, env }) {
  const credentials = statsCredentials(env);
  if (!credentials) return json({ error: "Stats authentication is not configured." }, 503);
  let body;
  try { body = await request.json(); } catch { return json({ error: "Enter a username and password." }, 400); }
  if (!(await credentialsMatch(body?.username, body?.password, env)))
    return json({ error: "Username or password is incorrect." }, 401);
  const session = await createStatsSession(credentials.username, env);
  return json({ authenticated: true, username: credentials.username }, 200,
    { "Set-Cookie": setStatsCookie(session) });
}

export async function onRequestDelete() {
  return json({ authenticated: false }, 200, { "Set-Cookie": clearStatsCookie() });
}
