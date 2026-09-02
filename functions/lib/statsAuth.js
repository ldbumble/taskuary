// Authentication shared by the stats login endpoint and the analytics reader.
// This is deliberately a tiny, hardcoded admin account. Change these two values and redeploy;
// changing the password also invalidates every existing signed session.

export const STATS_COOKIE = "__Host-taskuary_stats";
export const SESSION_SECONDS = 12 * 60 * 60;
export const STATS_USERNAME = "admin";
export const STATS_PASSWORD = "taskuary-stats";

const encoder = new TextEncoder();
const b64url = (bytes) => btoa(String.fromCharCode(...bytes))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (value) => {
  const padded = String(value || "").replace(/-/g, "+").replace(/_/g, "/")
    .padEnd(Math.ceil(String(value || "").length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
};

export function statsCredentials() {
  return { username: STATS_USERNAME, password: STATS_PASSWORD };
}

async function keyFor(password) {
  return crypto.subtle.importKey("raw", encoder.encode(password),
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

export async function credentialsMatch(username, password) {
  const expected = statsCredentials();
  const [userOK, passwordOK] = await Promise.all([
    safeEqual(username || "", expected.username), safeEqual(password || "", expected.password),
  ]);
  return userOK && passwordOK;
}

export async function createStatsSession(username, now = Date.now()) {
  const { password } = statsCredentials();
  const body = b64url(encoder.encode(JSON.stringify({
    u: String(username), exp: Math.floor(now / 1000) + SESSION_SECONDS,
  })));
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", await keyFor(password), encoder.encode(body)));
  return `${body}.${b64url(signature)}`;
}

export async function verifyStatsSession(value, now = Date.now()) {
  try {
    const { username, password } = statsCredentials();
    const [body, signature, extra] = String(value || "").split(".");
    if (!body || !signature || extra) return false;
    const valid = await crypto.subtle.verify("HMAC", await keyFor(password),
      unb64url(signature), encoder.encode(body));
    if (!valid) return false;
    const session = JSON.parse(new TextDecoder().decode(unb64url(body)));
    return session.u === username && Number(session.exp) > Math.floor(now / 1000);
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

export const hasStatsSession = (request) => verifyStatsSession(cookieValue(request));
export const setStatsCookie = (value) => `${STATS_COOKIE}=${value}; Path=/; Max-Age=${SESSION_SECONDS}; HttpOnly; Secure; SameSite=Strict`;
export const clearStatsCookie = () => `${STATS_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`;
