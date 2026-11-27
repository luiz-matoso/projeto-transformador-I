import { mkdir, copyFile } from "node:fs/promises";
for (const route of [
  "login",
  "perfis",
  "demonstracao/perfis",
  "demonstracao/analisar",
  "dataset",
  "anotacao",
  "demonstracao",
]) {
  await mkdir(`dist/${route}`, { recursive: true });
  await copyFile("dist/index.html", `dist/${route}/index.html`);
}
await copyFile("dist/index.html", "dist/404.html");
