export interface LocalImage {
  key: string;
  file: File;
}
export interface WritableHandle {
  getFile(): Promise<File>;
  createWritable(): Promise<{
    write(data: string): Promise<void>;
    close(): Promise<void>;
    abort?(): Promise<void>;
  }>;
}
export interface DirectoryHandle {
  kind: "directory";
  name: string;
  values(): AsyncIterable<
    DirectoryHandle | ({ kind: "file"; name: string } & WritableHandle)
  >;
  getFileHandle(
    name: string,
    options?: { create: boolean },
  ): Promise<WritableHandle>;
  requestPermission(options: { mode: "readwrite" }): Promise<string>;
}
export type PickerWindow = Window & {
  showDirectoryPicker?: (options: { mode: "read" }) => Promise<DirectoryHandle>;
  showOpenFilePicker?: (options: unknown) => Promise<WritableHandle[]>;
};
export function imageKey(path: string) {
  path = path.replaceAll("\\", "/");
  const index = path.indexOf("/images/");
  if (index >= 0) return path.slice(index + 8);
  return path.startsWith("images/") ? path.slice(7) : path;
}
export function fileImages(files: File[]): LocalImage[] {
  const images = files
    .filter((f) => /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i.test(f.name))
    .map((file) => ({
      file,
      key: imageKey(
        file.webkitRelativePath
          ? file.webkitRelativePath.split("/").slice(1).join("/")
          : file.name,
      ),
    }));
  if (new Set(images.map((f) => f.key)).size !== images.length)
    throw new Error(
      "Há imagens com caminhos duplicados. Importe a pasta preservando os subdiretórios.",
    );
  return images.sort((a, b) => a.key.localeCompare(b.key));
}
export async function directoryFiles(
  root: DirectoryHandle,
  prefix = "",
): Promise<{ file: File; path: string; handle: WritableHandle }[]> {
  const result: { file: File; path: string; handle: WritableHandle }[] = [];
  for await (const entry of root.values()) {
    if (entry.name.startsWith(".") || entry.name === "node_modules") continue;
    if (entry.kind === "directory")
      result.push(...(await directoryFiles(entry, prefix + entry.name + "/")));
    else
      result.push({
        file: await entry.getFile(),
        path: prefix + entry.name,
        handle: entry,
      });
  }
  return result;
}
export async function readImages(
  files: { file: File; path: string }[],
): Promise<LocalImage[]> {
  const images = files
    .filter((f) => /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i.test(f.file.name))
    .map((f) => ({ key: imageKey(f.path), file: f.file }));
  if (new Set(images.map((f) => f.key)).size !== images.length)
    throw new Error("Há imagens com caminhos duplicados.");
  return images.sort((a, b) => a.key.localeCompare(b.key));
}
export async function dimensions(file: File) {
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return [image.naturalWidth, image.naturalHeight] as const;
  } finally {
    URL.revokeObjectURL(url);
  }
}
export async function fileHash(file: File) {
  return Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
    ),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
}
