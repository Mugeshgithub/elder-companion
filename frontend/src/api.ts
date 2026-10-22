// In production the screen talks to a server-side proxy that holds the backend secret.
// The proxy also wants an access code, typed once on this device, so a public URL does not expose alerts.
const KEY = "ec-access-code";

export const getCode = () => {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
};

export const saveCode = (code: string) => {
  try {
    localStorage.setItem(KEY, code);
  } catch {
    /* private window: the code just has to be typed again next time */
  }
};

export async function api(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const code = getCode();
  if (code) headers.set("x-access-code", code);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (res.status === 401) window.dispatchEvent(new Event("ec-locked"));
  return res;
}
