import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { parseCSV } from "../../src/features/dataset/csv";
const directoryName = "ergonomics-fixture";
function serialize(rows: Record<string, string>[]) {
  const keys = Object.keys(rows[0]);
  const escape = (v: string) => '"' + v.replaceAll('"', '""') + '"';
  return (
    keys.join(",") +
    "\r\n" +
    rows.map((r) => keys.map((k) => escape(r[k] || "")).join(",")).join("\r\n")
  );
}
async function setup(page: any) {
  const [source] = parseCSV(
    await readFile(
      path.resolve("../data/dataset-v4/transitability_annotations.csv"),
      "utf8",
    ),
  );
  const image = (
    await readFile(path.resolve("../data/dataset-v4/images", source.filename))
  ).toString("base64");
  const base = {
    ...source,
    passage_width: "adequate",
    obstruction: "none",
    surface_condition: "regular",
    level_change: "none",
    path_continuity: "continuous",
    ramp_condition: "not_applicable",
    curb_access: "not_applicable",
    slope: "unknown",
    detour: "unknown",
    annotation_confidence: "high",
    obstacle_type: "[]",
    surface_obstacle: "[]",
    obstacle_instances: "[]",
    workflow_status: "pending_review",
    annotator_id: "historic-author",
    review_acknowledged: "false",
    source_metadata: '{"fixture":true,"preserve":7}',
    comment: "Original fixture note",
    reviewed_at: "2026-10-01",
    circulation_path_status: "annotated",
    circulation_path: "[[[0.1,0.6],[0.8,0.6],[0.8,0.9],[0.1,0.9]]]",
    image_width: "1440",
    image_height: "960",
  };
  const rows = [
    { ...base, filename: "first.png" },
    { ...base, filename: "second.png", annotator_id: "" },
    {
      ...base,
      filename: "portrait.png",
      annotator_id: "",
      image_width: "960",
      image_height: "1440",
    },
  ];
  await page.addInitScript(() => {
    const expiresAt = Date.now() + 3600000;
    sessionStorage.setItem(
      "permear.session.v1",
      JSON.stringify({
        token:
          "e30." +
          btoa(JSON.stringify({ exp: Math.floor(expiresAt / 1000) })) +
          ".test-only",
        username: "ergonomics-user",
        expiresAt,
      }),
    );
  });
  await page.route("**/api/**", (r: any) =>
    r.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.goto("/dataset");
  await page.evaluate(
    async ({ image, csv, name }) => {
      const directory = await (
        await navigator.storage.getDirectory()
      ).getDirectoryHandle(name, { create: true });
      const images = await directory.getDirectoryHandle("images", {
        create: true,
      });
      const bytes = Uint8Array.from(atob(image), (c) => c.charCodeAt(0));
      const bitmap = await createImageBitmap(
        new Blob([bytes], { type: "image/png" }),
      );
      for (const file of ["first.png", "second.png", "portrait.png"]) {
        const canvas = document.createElement("canvas");
        canvas.width = file === "portrait.png" ? 960 : 1440;
        canvas.height = file === "portrait.png" ? 1440 : 960;
        canvas
          .getContext("2d")!
          .drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise<Blob>((resolve) =>
          canvas.toBlob((b) => resolve(b!), "image/png"),
        );
        const writer = await (
          await images.getFileHandle(file, { create: true })
        ).createWritable();
        await writer.write(blob);
        await writer.close();
      }
      bitmap.close();
      const writer = await (
        await directory.getFileHandle("transitability_annotations.csv", {
          create: true,
        })
      ).createWritable();
      await writer.write(csv);
      await writer.close();
      Object.defineProperty(window, "showDirectoryPicker", {
        configurable: true,
        value: async () => directory,
      });
    },
    { image, csv: serialize(rows), name: directoryName },
  );
  await page.getByText("Abrir dataset", { exact: true }).click();
  await page
    .getByRole("button", { name: "Abrir pasta local", exact: true })
    .click();
  await expect(page.locator(".dataset-summary")).toContainText("3 imagens");
  await page
    .getByRole("button", { name: "Anotar", exact: false })
    .first()
    .click();
}
async function diskRows(page: any) {
  return parseCSV(
    await page.evaluate(async (name) => {
      const d = await (
        await navigator.storage.getDirectory()
      ).getDirectoryHandle(name);
      return (
        await (
          await d.getFileHandle("transitability_annotations.csv")
        ).getFile()
      ).text();
    }, directoryName),
  );
}
async function choose(page: any, field: string, value: string) {
  await page
    .getByRole("radiogroup", { name: field, exact: true })
    .getByText(value, { exact: true })
    .click();
}
async function layout(page: any) {
  await expect
    .poll(() =>
      page
        .locator(".polygon-frame")
        .evaluate((e: HTMLElement) => e.offsetHeight),
    )
    .toBeGreaterThan(40);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollHeight <= innerHeight + 1,
    ),
  ).toBe(true);
  const image = page.locator(".polygon-frame > img");
  const before = await image.boundingBox();
  expect(before).not.toBeNull();
  const natural = await image.evaluate(
    (e: HTMLImageElement) => e.naturalWidth / e.naturalHeight,
  );
  expect(before!.width / before!.height).toBeCloseTo(natural, 2);
  const svg = await page.locator(".polygon-frame svg").boundingBox();
  expect(svg!.width).toBeCloseTo(before!.width, 1);
  expect(svg!.height).toBeCloseTo(before!.height, 1);
  await page
    .getByLabel("Painel de atributos", { exact: true })
    .evaluate((e: HTMLElement) => (e.scrollTop = 600));
  await expect
    .poll(() =>
      page
        .getByLabel("Painel de atributos", { exact: true })
        .evaluate((e: HTMLElement) => e.scrollTop),
    )
    .toBeGreaterThan(0);
  expect(await image.boundingBox()).toEqual(before);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await expect(
    page.getByRole("button", { name: "Salvar", exact: true }),
  ).toBeInViewport();
  await expect(
    page.getByRole("button", { name: "Finalizar e próxima", exact: true }),
  ).toBeInViewport();
  await expect(
    page.getByRole("button", { name: "Desenhar", exact: true }),
  ).toBeInViewport();
  await expect(
    page.getByRole("navigation", { name: "Navegar pelas imagens" }),
  ).toBeInViewport();
}
test("fixed workspace, one-click choices, review confirmation, save and resume", async ({
  page,
}) => {
  await setup(page);
  for (const size of [
    { width: 1440, height: 960 },
    { width: 1280, height: 720 },
  ]) {
    await page.setViewportSize(size);
    await layout(page);
  }
  await choose(page, "Largura livre de passagem", "Ampla");
  await expect(
    page
      .getByRole("radiogroup", {
        name: "Largura livre de passagem",
        exact: true,
      })
      .getByRole("radio", { name: "Ampla", exact: true }),
  ).toBeChecked();
  const objectGroup = page.getByRole("group", {
    name: "Tipos de obstáculo relevantes",
    exact: true,
  });
  await objectGroup
    .getByRole("button", { name: "Veículo", exact: true })
    .click();
  await expect(
    objectGroup.getByRole("button", { name: "Veículo", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(await page.getByRole("checkbox").count()).toBe(0);
  const panel = page.getByLabel("Painel de atributos", { exact: true });
  await panel.evaluate((e: HTMLElement) => (e.scrollTop = e.scrollHeight));
  const frameBeforeSave = await page.locator(".polygon-frame").boundingBox();
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Anotação salva no CSV local.")).toBeVisible();
  await expect
    .poll(() => page.locator(".polygon-frame").boundingBox())
    .toEqual(frameBeforeSave);
  let rows = await diskRows(page);
  expect(rows[0].passage_width).toBe("wide");
  expect(JSON.parse(rows[0].obstacle_type)).toEqual(["vehicle"]);
  expect(rows[0].annotator_id).toBe("historic-author");
  expect(rows[0].review_acknowledged).toBe("false");
  expect(rows[1].comment).toBe("Original fixture note");
  await page
    .getByRole("button", { name: "Finalizar e próxima", exact: true })
    .click();
  await expect(page.locator(".annotation-filename strong")).toHaveText(
    "portrait.png",
  );
  await expect
    .poll(() => panel.evaluate((e: HTMLElement) => e.scrollTop))
    .toBe(0);
  rows = await diskRows(page);
  expect(rows[0].workflow_status).toBe("finalized");
  expect(rows[0].review_acknowledged).toBe("true");
  expect(rows[0].reviewed_at).not.toBe("2026-10-01");
  expect(JSON.parse(rows[0].source_metadata)).toMatchObject({
    preserve: 7,
    workspace_reviews: [{ by: "ergonomics-user" }],
  });
  await layout(page);
  await page
    .getByLabel("Comentário", { exact: true })
    .fill("Saved after advancing");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Anotação salva no CSV local.")).toBeVisible();
  rows = await diskRows(page);
  expect(rows.find((r) => r.filename === "portrait.png")!.annotator_id).toBe(
    "ergonomics-user",
  );
  await page.reload();
  await expect(page.locator(".annotation-filename strong")).toHaveText(
    "portrait.png",
  );
  await expect(page.getByLabel("Comentário", { exact: true })).toHaveValue(
    "Saved after advancing",
  );
  await expect
    .poll(() => panel.evaluate((e: HTMLElement) => e.scrollTop))
    .toBe(0);
  await page.setViewportSize({ width: 1440, height: 960 });
  await panel.evaluate((e: HTMLElement) => (e.scrollTop = 0));
  await page.setViewportSize({ width: 390, height: 844 });
  await layout(page);
});
test("drawing tools and obstacle details stay usable without moving the image", async ({
  page,
}) => {
  await setup(page);
  await page.getByRole("button", { name: "Desenhar", exact: true }).click();
  let box = (await page
    .getByLabel("Editor da faixa de circulação")
    .boundingBox())!;
  for (const [x, y] of [
    [0.1, 0.1],
    [0.4, 0.1],
    [0.3, 0.4],
  ])
    await page.mouse.click(box.x + x * box.width, box.y + y * box.height);
  await page
    .getByRole("button", { name: "Fechar polígono", exact: true })
    .click();
  await expect(page.locator(".polygon-frame polygon")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Obstáculos espaciais", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delimitar obstáculo", exact: true })
    .click();
  box = (await page
    .getByLabel("Editor de caixas de obstáculos")
    .boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.1, box.y + box.height * 0.1);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.4, box.y + box.height * 0.4);
  await page.mouse.up();
  await page
    .getByLabel("Tipo do objeto 1", { exact: true })
    .selectOption("vehicle");
  await page
    .getByLabel("Relação com a faixa 1", { exact: true })
    .selectOption("outside");
  const before = await page.locator(".polygon-frame").boundingBox();
  await page
    .getByLabel("Painel de atributos", { exact: true })
    .evaluate((e: HTMLElement) => (e.scrollTop = e.scrollHeight));
  expect(await page.locator(".polygon-frame").boundingBox()).toEqual(before);
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Anotação salva no CSV local.")).toBeVisible();
  const rows = await diskRows(page);
  expect(JSON.parse(rows[0].obstacle_instances)[0]).toMatchObject({
    type: "vehicle",
    path_relation: "outside",
  });
  expect(JSON.parse(rows[0].circulation_path)).toHaveLength(2);
});


test("refinement: definitions preserve unsaved attributes, polygon draft and independent layout", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 1440, height: 960 });
  const sidebar = page.getByRole("navigation", { name: "Navegação principal" });
  await expect(sidebar.getByText("Modelos", { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText("Demonstração", { exact: true })).toBeVisible();
  await expect(sidebar.getByRole("link", { name: "Perfis", exact: true })).toHaveAttribute("href", /demonstracao\/perfis$/);
  await expect(sidebar.getByRole("link", { name: "Analisar trecho", exact: true })).toHaveAttribute("href", /demonstracao\/analisar$/);
  await expect(sidebar.getByRole("link", { name: "Demonstração", exact: true })).toHaveCount(0);
  await expect(page.getByText(/^Revisor:/)).toHaveCount(0);
  await expect(page.locator(".annotation-help")).toHaveCount(0);
  await choose(page, "Largura livre de passagem", "Estreita");
  const choices = page.getByRole("radiogroup", { name: "Largura livre de passagem", exact: true });
  const cells = await choices.locator("label").evaluateAll(elements => elements.map(e => ({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})));
  expect(Math.max(...cells.map(e => e.width)) - Math.min(...cells.map(e => e.width))).toBeLessThan(1);
  expect(new Set(cells.map(e => e.height)).size).toBe(1);
  const panel = page.getByLabel("Painel de atributos", { exact: true });
  await page.getByRole("button", { name: "Desenhar", exact: true }).click();
  const editor = page.getByLabel("Editor da faixa de circulação", { exact: true });
  const box = (await editor.boundingBox())!;
  for (const [x,y] of [[.1,.1],[.4,.1],[.3,.4]]) await page.mouse.click(box.x+x*box.width,box.y+y*box.height);
  await expect(editor.locator(".draft")).toHaveCount(1);
  await panel.evaluate((e: HTMLElement) => e.scrollTop = 480);
  const scroll = await panel.evaluate((e: HTMLElement) => e.scrollTop);
  const image = await page.locator(".polygon-frame").boundingBox();
  await page.getByRole("tab", { name: "Definições", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Legenda das cores", exact: true })).toBeVisible();
  await expect(editor.locator(".draft")).toHaveCount(1);
  expect(await page.locator(".polygon-frame").boundingBox()).toEqual(image);
  await expect(page.getByRole("button", { name: "Salvar", exact: true })).toBeInViewport();
  await page.getByRole("tab", { name: "Anotação", exact: true }).click();
  await expect(choices.getByRole("radio", {name:"Estreita",exact:true})).toBeChecked();
  expect(await panel.evaluate((e: HTMLElement) => e.scrollTop)).toBe(scroll);
  await page.getByRole("tab", { name: "Anotação", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", {name:"Definições",exact:true})).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await expect(page.getByRole("tab", {name:"Anotação",exact:true})).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "Fechar polígono", exact: true }).click();
  await expect(editor.locator("polygon")).toHaveCount(2);
  await expect(page.locator(".annotation-filename")).toContainText("alterações não salvas");
  expect((await diskRows(page))[0].passage_width).toBe("adequate");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Anotação salva no CSV local.")).toBeVisible();
  expect((await diskRows(page))[0].passage_width).toBe("narrow");
  await page.reload();
  await expect(page.getByRole("radio", {name:"Estreita",exact:true})).toBeChecked();
  for (const size of [{width:1280,height:720},{width:390,height:844}]) {
    await page.setViewportSize(size);
    await layout(page);
  }
});

test("refinement: demonstration routes and home shortcuts share the same hierarchy", async ({page}) => {
  await setup(page);
  await page.getByRole("link", {name:"Início",exact:true}).click();
  await page.locator(".module-card").filter({has:page.getByRole("heading",{name:"Analisar trecho",exact:true})}).click();
  await expect(page).toHaveURL(/demonstracao\/analisar$/);
  await expect(page.getByRole("heading",{name:"Analisar trecho",exact:true})).toBeVisible();
  await page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link",{name:"Perfis",exact:true}).click();
  await expect(page).toHaveURL(/demonstracao\/perfis$/);
  await expect(page.getByRole("heading",{name:"Perfis",exact:true})).toBeVisible();
  await page.goto("/perfis");
  await expect(page).toHaveURL(/demonstracao\/perfis$/);
});
