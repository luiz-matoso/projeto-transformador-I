// IndexedDB stores file handles (direct access) or imported Files once; rows remain small.
export async function datasetCache<T>(key: string): Promise<T | undefined> {
  return transact("readonly", (store) => store.get(key));
}
export async function cacheDataset(key: string, value: unknown): Promise<void> {
  await transact("readwrite", (store) => store.put(value, key));
}
async function transact(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest,
): Promise<any> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const open = indexedDB.open("permear-annotations-v4", 1);
    open.onupgradeneeded = () => open.result.createObjectStore("workspace");
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
  });
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("workspace", mode);
      const request = action(tx.objectStore("workspace"));
      tx.oncomplete = () => resolve(request.result);
      tx.onabort = () => reject(tx.error);
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
