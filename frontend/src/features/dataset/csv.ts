import type { Row } from "../../types/index";
export function parseCSV(text: string): Row[] {
  const matrix: string[][] = [];
  let row: string[] = [],
    cell = "",
    quoted = false;
  text = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (!quoted && cell) {
        throw new Error("CSV inválido: aspas fora de um campo.");
      } else quoted = !quoted;
    } else if (c === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((c === "\n" || c === "\r") && !quoted) {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some(Boolean)) matrix.push(row);
      row = [];
      cell = "";
    } else cell += c;
  }
  if (quoted) throw new Error("CSV inválido: aspas não fechadas.");
  row.push(cell);
  if (row.some(Boolean)) matrix.push(row);
  const headers = matrix.shift() || [];
  if (new Set(headers).size !== headers.length)
    throw new Error("CSV com colunas duplicadas.");
  return matrix.map((cells) => {
    if (cells.length !== headers.length)
      throw new Error("CSV com número de colunas inconsistente.");
    return Object.fromEntries(headers.map((h, i) => [h, cells[i]]));
  });
}
