import {
  clearStatsCookie, createStatsSession, credentialsMatch, hasStatsSession,
  setStatsCookie, statsCredentials,
} from "../lib/statsAuth.js";

const json = (body, status = 200, headers = {}) => Response.json(body, {
  status, headers: { "Cache-Control": "no-store", ...headers },
});

export async function onRequestGet({ request }) {
  const authenticated = await hasStatsSession(request);
  return json({ authenticated, username: authenticated ? statsCredentials().username : null });
}

export async function onRequestPost({ request }) {
  let body;
  try { body = await request.json(); } catch { return json({ error: "Enter a username and password." }, 400); }
  if (!(await credentialsMatch(body?.username, body?.password)))
    return json({ error: "Username or password is incorrect." }, 401);
  const session = await createStatsSession(statsCredentials().username);
  return json({ authenticated: true, username: statsCredentials().username }, 200,
    { "Set-Cookie": setStatsCookie(session) });
}

export async function onRequestDelete() {
  return json({ authenticated: false }, 200, { "Set-Cookie": clearStatsCookie() });
}
