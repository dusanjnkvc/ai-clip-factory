export async function api(path: string, options: RequestInit = {}) {
  if (process.env.NEXT_PUBLIC_BROWSER_MODE === 'true') {
    const { browserApi } = await import('./browser-api');
    return browserApi(path,options);
  }
  const response = await fetch("/api" + path, {
    credentials: "include",
    ...options,
    headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { detail = "Service returned " + response.status; }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.status === 204 ? null : response.json();
}

export async function downloadArtifact(path: string) {
  if (process.env.NEXT_PUBLIC_BROWSER_MODE === 'true') {
    const { browserDownload } = await import('./browser-api');
    await browserDownload(path);
    return;
  }
  const anchor=document.createElement('a');
  anchor.href='/api'+path;
  anchor.download='';
  anchor.click();
}
