import type { Point, Polygons } from "../../types/index";
// Contornos externos em uma grade reduzida; a revisão humana continua obrigatória.
export async function maskPolygons(base64: string): Promise<Polygons> {
  const image = new Image();
  image.src = "data:image/png;base64," + base64;
  await image.decode();
  const w = Math.min(160, image.width),
    h = Math.max(1, Math.round((image.height * w) / image.width));
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d")!;
  ctx.drawImage(image, 0, 0, w, h);
  const pixels = ctx.getImageData(0, 0, w, h).data;
  const inside = (x: number, y: number) =>
    x >= 0 && y >= 0 && x < w && y < h && pixels[(y * w + x) * 4] >= 128;
  const edges = new Map<string, Point[]>();
  const add = (a: Point, b: Point) => {
    const k = a.join(",");
    edges.set(k, [...(edges.get(k) || []), b]);
  };
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++)
      if (inside(x, y)) {
        if (!inside(x, y - 1)) add([x, y], [x + 1, y]);
        if (!inside(x + 1, y)) add([x + 1, y], [x + 1, y + 1]);
        if (!inside(x, y + 1)) add([x + 1, y + 1], [x, y + 1]);
        if (!inside(x - 1, y)) add([x, y + 1], [x, y]);
      }
  const result: Polygons = [];
  while (edges.size) {
    const first = edges.keys().next().value!;
    let current: Point = first.split(",").map(Number) as Point;
    const path: Point[] = [];
    let safety = 0;
    do {
      path.push(current);
      const k = current.join(",");
      const next = edges.get(k);
      if (!next?.length) break;
      current = next.pop()!;
      if (!next.length) edges.delete(k);
      if (++safety > w * h * 8) break;
    } while (current.join(",") !== first);
    const area =
      path.reduce((sum, p, i) => {
        const q = path[(i + 1) % path.length];
        return sum + p[0] * q[1] - q[0] * p[1];
      }, 0) / 2;
    if (area < Math.max(3, w * h * 0.0005)) continue;
    const simplified = path
      .filter((p, i) => {
        const a = path[(i + path.length - 1) % path.length],
          b = path[(i + 1) % path.length];
        return (p[0] - a[0]) * (b[1] - p[1]) !== (p[1] - a[1]) * (b[0] - p[0]);
      })
      .filter(
        (_, i, all) =>
          all.length < 120 || i % Math.ceil(all.length / 120) === 0,
      );
    if (simplified.length >= 3)
      result.push(simplified.map((p) => [p[0] / w, p[1] / h]));
  }
  return result;
}
