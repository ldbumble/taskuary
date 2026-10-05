// Authentication shared by the stats login endpoint and the analytics reader.
// Credentials belong in deployment secrets. Missing or incomplete configuration
// cannot issue or validate a session; changing either secret invalidates old cookies.

export const STATS_COOKIE = "__Host-taskuary_stats";
export const SESSION_SECONDS = 12 * 60 * 60;

const encoder = new TextEncoder();
const b64url = (bytes) => btoa(String.fromCharCode(...bytes))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (value) => {
  const padded = String(value || "").replace(/-/g, "+").replace(/_/g, "/")
    .padEnd(Math.ceil(String(value || "").length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
};

export function statsCredentials(env = {}) {
  const password = env.STATS_PASSWORD;
  const sessionSecret = env.STATS_SESSION_SECRET;
  if (typeof password !== "string" || !password
      || typeof sessionSecret !== "string" || encoder.encode(sessionSecret).length < 32) return null;
  const username = typeof env.STATS_USERNAME === "string" && env.STATS_USERNAME ? env.STATS_USERNAME : "admin";
  return { username, password, sessionSecret };
}

async function keyFor(credentials) {
  // JSON preserves the boundary between the independent session secret and password.
  // Binding both means rotating either one revokes every existing session.
  const material = encoder.encode(JSON.stringify([credentials.sessionSecret, credentials.password]));
  return crypto.subtle.importKey("raw", material,
    { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

async function safeEqual(left, right) {
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(String(left))),
    crypto.subtle.digest("SHA-256", encoder.encode(String(right))),
  ]);
  const aa = new Uint8Array(a), bb = new Uint8Array(b);
  let different = 0;
  for (let i = 0; i < aa.length; i += 1) different |= aa[i] ^ bb[i];
  return different === 0;
}

export async function credentialsMatch(username, password, env) {
  const expected = statsCredentials(env);
  if (!expected) return false;
  const [userOK, passwordOK] = await Promise.all([
    safeEqual(username || "", expected.username), safeEqual(password || "", expected.password),
  ]);
  return userOK && passwordOK;
}

export async function createStatsSession(username, env, now = Date.now()) {
  const credentials = statsCredentials(env);
  if (!credentials) throw new Error("Stats authentication is not configured.");
  const body = b64url(encoder.encode(JSON.stringify({
    u: String(username), exp: Math.floor(now / 1000) + SESSION_SECONDS,
  })));
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", await keyFor(credentials), encoder.encode(body)));
  return `${body}.${b64url(signature)}`;
}

export async function verifyStatsSession(value, env, now = Date.now()) {
  try {
    const credentials = statsCredentials(env);
    if (!credentials) return false;
    const [body, signature, extra] = String(value || "").split(".");
    if (!body || !signature || extra) return false;
    const valid = await crypto.subtle.verify("HMAC", await keyFor(credentials),
      unb64url(signature), encoder.encode(body));
    if (!valid) return false;
    const session = JSON.parse(new TextDecoder().decode(unb64url(body)));
    return session.u === credentials.username && Number.isFinite(session.exp)
      && session.exp > Math.floor(now / 1000);
  } catch { return false; }
}

const cookieValue = (request) => {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (name === STATS_COOKIE) return value.join("=");
  }
  return "";
};

export const hasStatsSession = (request, env) => verifyStatsSession(cookieValue(request), env);
export const setStatsCookie = (value) => `${STATS_COOKIE}=${value}; Path=/; Max-Age=${SESSION_SECONDS}; HttpOnly; Secure; SameSite=Strict`;
export const clearStatsCookie = () => `${STATS_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`;
