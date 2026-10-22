// Vercel function: the browser calls /api/*, this forwards to the backend with the shared secret added.
// It only forwards the routes the screens use, and only with the right access code.
const ALLOWED = [
  /^dashboard\/\d+$/,
  /^inspect\/\d+$/,
  /^setup\/\d+$/,
  /^opener\/\d+$/,
  /^checkin\/\d+$/,
  /^activity\/\d+$/,
  /^alerts\/\d+\/\d+\/resolve$/,
];

const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export default {
  async fetch(request: Request): Promise<Response> {
    const { ACCESS_CODE, AGENT_SHARED_SECRET, BACKEND_URL } = process.env;
    if (!ACCESS_CODE || !AGENT_SHARED_SECRET || !BACKEND_URL) return json({ detail: "not configured" }, 500);
    if (request.headers.get("x-access-code") !== ACCESS_CODE) return json({ detail: "unauthorized" }, 401);

    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/api\//, "");
    if (!ALLOWED.some((re) => re.test(path))) return json({ detail: "not found" }, 404);
    if (request.method !== "GET" && request.method !== "POST") return json({ detail: "method not allowed" }, 405);

    try {
      const res = await fetch(`${BACKEND_URL.replace(/\/$/, "")}/${path}${url.search}`, {
        method: request.method,
        headers: { "x-api-key": AGENT_SHARED_SECRET },
        signal: AbortSignal.timeout(15000),
      });
      return new Response(res.body, { status: res.status, headers: { "content-type": "application/json" } });
    } catch {
      return json({ detail: "backend unreachable" }, 502);
    }
  },
};
