/** Browser-only persistence. Media never leaves this browser's origin. */
export type BrowserRow = Record<string, any>;
let database: Promise<IDBDatabase> | undefined;

function openDatabase(): Promise<IDBDatabase> {
  if (!database) database = new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) return reject(new Error("This browser does not support local IndexedDB storage."));
    const request = indexedDB.open("ai-clip-factory-local-v1", 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("records", { keyPath: "key" });
      request.result.createObjectStore("files", { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => { database = undefined; reject(new Error("Local storage could not be opened. Allow site storage in this browser.")); };
    request.onblocked = () => reject(new Error("Close older AI Clip Factory tabs before upgrading local storage."));
  });
  return database;
}

async function transaction<T>(store: string, mode: IDBTransactionMode, perform: (objectStore: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode);
    const request = perform(tx.objectStore(store));
    let result: T;
    request.onsuccess = () => { result = request.result; };
    request.onerror = () => reject(new Error(request.error?.name === "QuotaExceededError" ? "Browser storage is full. Download existing clips and free disk/site storage before continuing." : "A local storage operation failed."));
    tx.oncomplete = () => resolve(result);
    tx.onabort = () => reject(new Error(tx.error?.name === "QuotaExceededError" ? "Browser storage is full. Download important files before clearing site data." : "Local data could not be saved."));
    tx.onerror = () => reject(tx.error || new Error("Local data could not be saved."));
  });
}

export async function getRecord(table: string, id: string): Promise<BrowserRow | undefined> {
  const stored = await transaction<any>("records", "readonly", store => store.get(`${table}:${id}`));
  return stored?.value;
}

export async function setRecord(table: string, value: BrowserRow): Promise<BrowserRow> {
  await transaction("records", "readwrite", store => store.put({ key: `${table}:${value.id}`, value }));
  return value;
}

export async function claimQueuedJob(id: string, runner: string): Promise<BrowserRow | undefined> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('records', 'readwrite');
    const store = tx.objectStore('records');
    const request = store.get(`jobs:${id}`);
    let job: BrowserRow | undefined;
    request.onsuccess = () => {
      if (request.result?.value?.status !== 'queued') return;
      job = { ...request.result.value, status: 'processing', runner_id: runner, lease_until: Date.now() + 300000, attempts: Number(request.result.value.attempts || 0) + 1 };
      store.put({ key: `jobs:${id}`, value: job });
    };
    tx.oncomplete = () => resolve(job);
    tx.onerror = () => reject(tx.error || new Error('The local render queue could not claim a job.'));
    tx.onabort = () => reject(tx.error || new Error('The local render queue was interrupted.'));
  });
}

export async function modifyRecord(table: string, id: string, change: (current: BrowserRow) => BrowserRow): Promise<BrowserRow> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('records', 'readwrite'), store = tx.objectStore('records');
    const request = store.get(`${table}:${id}`);
    let value: BrowserRow;
    request.onsuccess = () => {
      if (!request.result?.value) { tx.abort(); return; }
      value = change(request.result.value);
      store.put({ key: `${table}:${id}`, value });
    };
    tx.oncomplete = () => resolve(value);
    tx.onerror = () => reject(tx.error || new Error('The local record could not be updated.'));
    tx.onabort = () => reject(new Error('The requested local record is unavailable.'));
  });
}

export async function listRecords(table: string): Promise<BrowserRow[]> {
  const rows = await transaction<any[]>("records", "readonly", store => store.getAll());
  return rows.filter(row => row.key.startsWith(`${table}:`)).map(row => row.value).sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

export async function putBlob(key: string, blob: Blob): Promise<void> {
  await transaction("files", "readwrite", store => store.put({ key, blob }));
}

export async function getBlob(key: string): Promise<Blob> {
  const stored = await transaction<any>("files", "readonly", store => store.get(key));
  if (!stored?.blob) throw new Error("This media file is unavailable in this browser. Import the authorized source again.");
  return stored.blob;
}

const blobUrls = new Map<string, string>();
export async function mediaUrl(key: string): Promise<string> {
  let url = blobUrls.get(key);
  if (!url) { url = URL.createObjectURL(await getBlob(key)); blobUrls.set(key, url); }
  return url;
}

export const timestamp = () => new Date().toISOString();
export const recordId = () => crypto.randomUUID();

export async function audit(action: string, entity_id: string, detail: BrowserRow = {}): Promise<void> {
  await setRecord("audit", { id: recordId(), created_at: timestamp(), action, entity_id, detail });
}
