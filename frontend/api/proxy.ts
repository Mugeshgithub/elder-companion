// Vercel function: the browser calls /api/*, this forwards to the backend with the shared secret added.
// It checks who is calling, and only forwards the routes that person is allowed to use.
// Declared here so this file compiles on Vercel without Node type definitions.
declare const process: { env: Record<string, string | undefined> };

// An owner (the owner code, or the companion's own device) may use everything the screens use.
const OWNER = [
  /^dashboard\/\d+$/,
  /^inspect\/\d+$/,
  /^opener\/\d+$/,
  /^checkin\/\d+$/,
  /^activity\/\d+$/,
  /^setup\/\d+$/,
  /^alerts\/\d+\/\d+\/resolve$/,
  /^family\/\d+\/(message|messages|summary|consent|pause|erase|privacy|retention|export|members)$/,
  /^family\/\d+\/members\/\d+\/revoke$/,
  /^family\/\d+\/notify$/,
  /^family\/\d+\/notify\/(link|words|test)$/,
  /^family\/\d+\/notify\/\d+\/remove$/,
  /^family\/\d+\/documents$/,
  /^family\/\d+\/documents\/medicines$/,
  /^family\/\d+\/documents\/\d+$/,
  /^family\/\d+\/documents\/\d+\/delete$/,
  /^family\/\d+\/documents\/\d+\/facts\/\d+$/,
];
// A family member (their own code) can read the portal, handle alerts, and leave messages. Nothing else.
const MEMBER = [/^dashboard\/\d+$/, /^alerts\/\d+\/\d+\/resolve$/, /^family\/\d+\/(message|messages|summary)$/];

type Who = { role: "owner" | "member"; name: string; patientId?: number };
const known = new Map<string, { who: Who; until: number }>(); // a code that just checked out is trusted for a minute

const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

async function authenticate(code: string, client: string, backend: string, secret: string, owner: string): Promise<Who | Response> {
  if (!code) return json({ detail: "unauthorized" }, 401);
  const hit = known.get(code);
  if (hit && hit.until > Date.now()) return hit.who;
  const res = await fetch(`${backend}/family/verify`, {
    method: "POST",
    headers: { "x-api-key": secret, "content-type": "application/json" },
    // the backend counts wrong codes per client address, so guessing is slowed down
    body: JSON.stringify({ code, client, master: code === owner }),
    signal: AbortSignal.timeout(10000),
  });
  if (res.status === 429) return json({ detail: "too many attempts" }, 429);
  if (!res.ok) return json({ detail: "unauthorized" }, 401);
  const d = await res.json();
  const who: Who = { role: d.role, name: d.name, patientId: d.patient_id };
  known.set(code, { who, until: Date.now() + 60_000 });
  return who;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const { ACCESS_CODE, AGENT_SHARED_SECRET, BACKEND_URL } = process.env;
    if (!ACCESS_CODE || !AGENT_SHARED_SECRET || !BACKEND_URL) return json({ detail: "not configured" }, 500);
    const backend = BACKEND_URL.replace(/\/$/, "");
    const client = (request.headers.get("x-forwarded-for") ?? "").split(",")[0].trim().slice(0, 80);

    let who: Who | Response;
    try {
      who = await authenticate(request.headers.get("x-access-code") ?? "", client, backend, AGENT_SHARED_SECRET, ACCESS_CODE);
    } catch {
      return json({ detail: "backend unreachable" }, 502);
    }
    if (who instanceof Response) return who;

    const url = new URL(request.url);
    const path = url.searchParams.get("path") ?? "";
    url.searchParams.delete("path");
    const rest = url.searchParams.toString();

    if (path === "whoami") return json({ role: who.role, name: who.name }, 200);
    if (!(who.role === "owner" ? OWNER : MEMBER).some((re) => re.test(path))) return json({ detail: "not found" }, 404);
    // a family member's code belongs to one person: the first number in every allowed path is that person's id
    if (who.role === "member" && Number(path.match(/\d+/)?.[0]) !== who.patientId) return json({ detail: "forbidden" }, 403);
    if (request.method !== "GET" && request.method !== "POST") return json({ detail: "method not allowed" }, 405);

    try {
      const res = await fetch(`${backend}/${path}${rest ? `?${rest}` : ""}`, {
        method: request.method,
        headers: {
          "x-api-key": AGENT_SHARED_SECRET,
          "x-actor": who.name,
          "content-type": request.headers.get("content-type") ?? "application/json",
        },
        body: request.method === "POST" ? await request.text() : undefined,
        signal: AbortSignal.timeout(25000),
      });
      return new Response(res.body, { status: res.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
    } catch {
      return json({ detail: "backend unreachable" }, 502);
    }
  },
};
