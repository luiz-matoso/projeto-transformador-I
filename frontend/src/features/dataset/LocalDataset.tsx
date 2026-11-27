import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import type { Row } from "../../types/index";
import {
  annotationRows,
  serializeCSV,
  downloadCSV,
  validateRow,
  parseCSV,
} from "../annotation/annotations";
import {
  directoryFiles,
  readImages,
  fileImages,
  dimensions,
  fileHash,
  type LocalImage,
  type DirectoryHandle,
  type WritableHandle,
  type PickerWindow,
} from "./files";
import { datasetCache, cacheDataset } from "./persistence";
import { migrateV4 } from "../annotation/v4";
interface DatasetState {
  cursor: string;
  setCursor: (key: string) => void;
  resume: () => Promise<void>;
  canResume: boolean;
  images: LocalImage[];
  rows: Record<string, Row>;
  manifest: Record<string, Row>;
  name: string;
  error: string;
  notice: string;
  loading: boolean;
  openDirectory: () => Promise<void>;
  importFiles: (files: File[]) => Promise<void>;
  openCSV: () => Promise<void>;
  importCSV: (file: File) => Promise<void>;
  saveRow: (row: Row, exportOnly?: boolean) => Promise<void>;
  exportAll: () => void;
  rowFor: (key: string) => Row | undefined;
}
const Context = createContext<DatasetState | null>(null);
export const useDataset = () => useContext(Context)!;
export function DatasetProvider({ children }: { children: ReactNode }) {
  const [cursor, setCursorState] = useState("");
  const [resumeRoot, setResumeRoot] = useState<DirectoryHandle | null>(null);
  const [images, setImages] = useState<LocalImage[]>([]),
    [rows, setRows] = useState<Record<string, Row>>({}),
    [manifest, setManifest] = useState<Record<string, Row>>({}),
    [name, setName] = useState("Nenhuma pasta selecionada");
  const [root, setRoot] = useState<DirectoryHandle | null>(null),
    [csv, setCSV] = useState<WritableHandle | null>(null),
    [hash, setHash] = useState<string | null>(null);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [loading, setLoading] = useState(false);
  async function migrate(
    text: string,
    localImages: LocalImage[],
    localManifest: Record<string, Row>,
  ) {
    const loaded = annotationRows(text);
    for (const row of loaded) {
      if (row.schema_version === "1") {
        const image = localImages.find(
          (i) =>
            i.key === row.filename ||
            localManifest[i.key]?.annotation_filename === row.filename ||
            (i.file.name === row.filename &&
              localImages.filter((f) => f.file.name === row.filename).length ===
                1),
        );
        if (!image)
          throw new Error(
            "CSV v1: selecione as imagens para recuperar as dimensões originais.",
          );
        const [w, h] = await dimensions(image.file);
        Object.assign(row, {
          image_width: String(w),
          image_height: String(h),
          circulation_path_status: "unknown",
          circulation_path: "[]",
        });
      }
      if (!["3", "4"].includes(row.schema_version))
        Object.assign(row, {
          schema_version: "3",
          circulation_path_origin: "manual",
        });
      Object.assign(row, migrateV4(row));
      validateRow(row);
    }
    return Object.fromEntries(loaded.map((r) => [r.filename, r]));
  }
  async function guarded(action: () => Promise<void>) {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      await action();
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError"))
        setError(
          e instanceof Error && e.message
            ? e.message
            : "Não foi possível abrir ou armazenar os arquivos. Use acesso direto à pasta para datasets grandes.",
        );
    } finally {
      setLoading(false);
    }
  }
  async function loadDirectory(handle: DirectoryHandle) {
    const entries = await directoryFiles(handle);
    const local = await readImages(entries);
    const m =
      entries.find((e) => e.file.name === "dataset_manifest.csv") ||
      entries.find((e) => e.file.name === "pilot_manifest.csv");
    const metadata = m
      ? Object.fromEntries(
          parseCSV(await m.file.text()).map((r) => [r.local_filename, r]),
        )
      : {};
    local.sort(
      (a, b) =>
        Number(metadata[a.key]?.queue_order || 0) -
        Number(metadata[b.key]?.queue_order || 0),
    );
    const candidates = entries.filter(
      (e) => e.file.name === "transitability_annotations.csv",
    );
    if (candidates.length > 1) throw Error("Há mais de um CSV de anotações.");
    const source = candidates[0];
    const loaded = source
      ? await migrate(await source.file.text(), local, metadata)
      : {};
    const sourceHash = source ? await fileHash(source.file) : null;
    setImages(local);
    setRows(loaded);
    setManifest(metadata);
    setName(handle.name);
    setRoot(handle);
    setCSV(source?.handle ?? null);
    setHash(sourceHash);
    setResumeRoot(null);
    await cacheDataset("source", { root: handle });
    await cacheDataset("state", {
      name: handle.name,
      rows: loaded,
      manifest: metadata,
      hash: sourceHash,
    });
  }
  async function resume() {
    if (resumeRoot)
      await guarded(async () => {
        if (
          (await (resumeRoot as any).requestPermission({ mode: "read" })) !==
          "granted"
        )
          throw Error("Autorize a leitura para retomar.");
        await loadDirectory(resumeRoot);
      });
  }
  function setCursor(key: string) {
    setCursorState(key);
    cacheDataset("cursor", key).catch(() =>
      setNotice("Não foi possível guardar a posição; o CSV permanece salvo."),
    );
  }
  useEffect(() => {
    let active = true;
    (async () => {
      const [source, saved, position] = await Promise.all([
        datasetCache<any>("source"),
        datasetCache<any>("state"),
        datasetCache<string>("cursor"),
      ]);
      if (!active || !source) return;
      setCursorState(position || "");
      if (source.root) {
        const permission = await source.root.queryPermission({ mode: "read" });
        if (!active) return;
        if (permission === "granted") await loadDirectory(source.root);
        else {
          setResumeRoot(source.root);
          setNotice(
            "Retome a pasta anterior para autorizar o acesso. O CSV e a posição foram preservados.",
          );
        }
      } else if (source.needsReselect) {
        setNotice(
          "O progresso está preservado. Reabra a pasta para recuperar as imagens; prefira Abrir pasta local.",
        );
      } else if (source.images && saved) {
        setImages(source.images);
        setRows(saved.rows);
        setManifest(saved.manifest);
        setName(saved.name);
        setNotice(
          "Dataset retomado do armazenamento local do navegador. Exporte o CSV como cópia de segurança.",
        );
      }
    })().catch(
      () =>
        active &&
        setNotice("Abra a pasta local para continuar pelo CSV salvo."),
    );
    return () => {
      active = false;
    };
  }, []);
  async function openDirectory() {
    await guarded(async () => {
      const pick = (window as PickerWindow).showDirectoryPicker;
      if (!pick) {
        setError(
          "Seu navegador não oferece acesso direto. Use Importar pasta ou arquivos.",
        );
        return;
      }
      const handle = await pick({ mode: "read" });
      await loadDirectory(handle);
    });
  }
  async function importFiles(files: File[]) {
    await guarded(async () => {
      const local = fileImages(files);
      const m =
        files.find((f) => f.name === "dataset_manifest.csv") ||
        files.find((f) => f.name === "pilot_manifest.csv");
      const metadata = m
        ? Object.fromEntries(
            parseCSV(await m.text()).map((r) => [r.local_filename, r]),
          )
        : {};
      const candidates = files.filter(
        (f) => f.name === "transitability_annotations.csv",
      );
      if (candidates.length > 1)
        throw new Error("Importe um único CSV de anotações.");
      let loaded = candidates[0]
        ? await migrate(await candidates[0].text(), local, metadata)
        : {};
      const saved = await datasetCache<any>("state");
      if (
        saved?.manifest &&
        Object.keys(metadata).length &&
        JSON.stringify(saved.manifest) === JSON.stringify(metadata)
      )
        loaded = { ...loaded, ...saved.rows };
      local.sort(
        (a, b) =>
          Number(metadata[a.key]?.queue_order || 0) -
          Number(metadata[b.key]?.queue_order || 0),
      );
      let cachedImages = true;
      try {
        await cacheDataset("source", { images: local });
      } catch {
        cachedImages = false;
        await cacheDataset("source", { needsReselect: true });
      }
      await cacheDataset("state", {
        rows: loaded,
        manifest: metadata,
        name:
          files[0]?.webkitRelativePath?.split("/")[0] || "Arquivos importados",
      });

      setImages(local);
      setRows(loaded);
      setManifest(metadata);
      setName(
        files[0]?.webkitRelativePath?.split("/")[0] || "Arquivos importados",
      );
      setRoot(null);
      setCSV(null);
      setHash(null);
      setNotice(
        cachedImages
          ? "Modo de importação: progresso salvo no navegador; exporte o CSV como cópia de segurança."
          : "Imagens abertas; espaço insuficiente para mantê-las no navegador. O progresso será salvo, mas após fechar será preciso reabrir a pasta. Prefira Abrir pasta local para retomada sem copiar imagens.",
      );
    });
  }
  async function importCSV(file: File) {
    await guarded(async () => {
      const loaded = await migrate(await file.text(), images, manifest);
      setRows(loaded);
      await cacheDataset("state", { rows: loaded, manifest, name });
      setCSV(null);
      setHash(null);
      setNotice("CSV carregado. Use Exportar CSV para guardar as alterações.");
    });
  }
  async function openCSV() {
    await guarded(async () => {
      const handles = await (window as PickerWindow).showOpenFilePicker!({
        multiple: false,
        types: [
          { description: "Anotações CSV", accept: { "text/csv": [".csv"] } },
        ],
      });
      const source = await handles[0].getFile();
      const loaded = await migrate(await source.text(), images, manifest);
      setRows(loaded);
      await cacheDataset("state", { rows: loaded, manifest, name });
      setCSV(handles[0]);
      setHash(await fileHash(source));
    });
  }
  const rowFor = (key: string) =>
    rows[key] ||
    rows[manifest[key]?.annotation_filename] ||
    (images.filter((i) => i.key.split("/").pop() === key.split("/").pop())
      .length === 1
      ? rows[key.split("/").pop()!]
      : undefined);
  async function saveRow(row: Row, exportOnly = false) {
    validateRow(row);
    const previous = rowFor(row.filename);
    const next = { ...rows };
    if (previous && previous.filename !== row.filename)
      delete next[previous.filename];
    next[row.filename] = row;
    setError("");
    setNotice("");
    let savedNotice = "";
    if ((root || csv) && !exportOnly) {
      let handle = csv;
      const permission =
        handle && "requestPermission" in handle
          ? await (
              handle as WritableHandle & {
                requestPermission: (v: {
                  mode: "readwrite";
                }) => Promise<string>;
              }
            ).requestPermission({ mode: "readwrite" })
          : root
            ? await root.requestPermission({ mode: "readwrite" })
            : "granted";
      if (permission !== "granted")
        throw new Error(
          "Gravação não autorizada. Exporte o CSV para salvar sem acesso direto.",
        );
      if (handle && hash && (await fileHash(await handle.getFile())) !== hash)
        throw new Error(
          "O CSV foi alterado fora do Workspace. Reabra o arquivo antes de salvar.",
        );
      if (!handle) {
        try {
          await root!.getFileHandle("transitability_annotations.csv");
          throw new Error(
            "Já existe um CSV não carregado. Abra-o antes de salvar.",
          );
        } catch (e) {
          if (!(e instanceof DOMException && e.name === "NotFoundError"))
            throw e;
        }
        handle = await root!.getFileHandle("transitability_annotations.csv", {
          create: true,
        });
      }
      const writer = await handle.createWritable();
      try {
        await writer.write(serializeCSV(Object.values(next)));
        await writer.close();
      } catch (error) {
        await writer.abort?.();
        throw error;
      }
      setHash(await fileHash(await handle.getFile()));
      setCSV(handle);
      savedNotice = "Anotação salva no CSV local.";
    } else {
      if (exportOnly) downloadCSV(Object.values(next));
      savedNotice = exportOnly
        ? "CSV exportado e progresso salvo neste navegador."
        : "Progresso salvo neste navegador. Exporte o CSV como cópia de segurança.";
    }
    try {
      await cacheDataset("state", { rows: next, manifest, name });
    } catch (error) {
      if (!root && !csv) throw error;
      savedNotice =
        "CSV salvo. A retomada automática não pôde ser gravada; reabra a pasta para continuar.";
    }
    setRows(next);
    setNotice(savedNotice);
  }
  return (
    <Context.Provider
      value={{
        cursor,
        setCursor,
        resume,
        canResume: !!resumeRoot,
        images,
        rows,
        manifest,
        name,
        error,
        notice,
        loading,
        openDirectory,
        importFiles,
        openCSV,
        importCSV,
        saveRow,
        exportAll: () => downloadCSV(Object.values(rows)),
        rowFor,
      }}
    >
      {children}
    </Context.Provider>
  );
}
