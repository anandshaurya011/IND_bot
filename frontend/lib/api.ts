export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export function errorMessage(status: number, data: any): string {
  const detail = data?.detail;
  const d = Array.isArray(detail?.errors)
    ? detail.errors.join("; ")
    : typeof detail === "string"
      ? detail
      : JSON.stringify(detail ?? data);
  return `${status}: ${d}`;
}

export async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  const currentPath = window.location?.pathname ?? "";
  if (res.status === 401) {
    if (!currentPath.startsWith("/sign-in")) window.location.assign("/sign-in");
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, data));
  return data as T;
}
