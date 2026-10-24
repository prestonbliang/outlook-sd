/** Bound read requests, with a single retry for temporary server failures. Never retries submissions. */
export async function fetchJSON<T>(url: string, options: RequestInit = {}): Promise<T> {
  const canRetry = ["GET", "HEAD"].includes((options.method ?? "GET").toUpperCase());
  for (let attempt = 0; attempt < 2; attempt++) {
    options.signal?.throwIfAborted();
    const signal = options.signal
      ? AbortSignal.any([options.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000);
    let response: Response;
    try { response = await fetch(url, { cache: "no-store", ...options, signal }); }
    catch (error) {
      if (options.signal?.aborted) throw error;
      throw new Error("Could not connect. Check your connection and try again.");
    }
    if (canRetry && attempt === 0 && [502, 503, 504].includes(response.status)) { await response.body?.cancel(); continue; }
    if (!response.ok) throw new Error(response.status === 404
      ? "This information is not available yet. Try refreshing the page."
      : "This information could not be loaded. Please try again.");
    try { return await response.json(); }
    catch { throw new Error("The service returned an unreadable response. Please try again."); }
  }
  throw new Error("This information could not be loaded. Please try again.");
}
