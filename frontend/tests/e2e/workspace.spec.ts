import { test, expect } from "@playwright/test";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
const evidence =
  process.env.WORKSPACE_EVIDENCE_DIR ||
  path.resolve("../artifacts/workspace-persistence");
test("fluxo real: login, inferência pareada, validade, importação e exportação de anotações", async ({
  page,
}) => {
  if (!process.env.WORKSPACE_TEST_PASSWORD)
    throw new Error(
      "Execute python -m scripts.validate_workspace para configurar a API real local.",
    );
  await mkdir(evidence, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Entrar", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".login-card")).toBeVisible();
  await expect(page.locator(".login-right")).toHaveCount(0);
  expect(
    await page
      .locator(".login-card")
      .evaluate((el) => getComputedStyle(el).backgroundColor),
  ).toBe("rgb(255, 255, 255)");
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "login.png"),
    fullPage: true,
  });
  await page
    .getByLabel("Usuário", { exact: true })
    .fill(process.env.WORKSPACE_TEST_USERNAME!);
  await page
    .getByLabel("Senha", { exact: true })
    .fill("incorrect-validation-only");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("inválidos");
  await page
    .getByLabel("Senha", { exact: true })
    .fill(process.env.WORKSPACE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Olá!", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "home.png"),
    fullPage: true,
  });
  await expect(page.locator(".module-card")).toHaveCount(4);
  for (const title of [
    "Início",
    "Dataset",
    "Anotação",
    "Perfis",
    "Demonstração",
  ])
    await expect(
      page.getByRole("link", { name: title, exact: true }),
    ).toBeVisible();
  for (const copy of [
    "Protótipo acadêmico",
    "Projeto Transformador I",
    "Ambiente de pesquisa",
  ])
    await expect(page.getByText(copy, { exact: true })).toHaveCount(0);
  const sidebarColor = await page
    .locator(".sidebar")
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  const channels = sidebarColor.match(/[0-9]+/g)!;
  expect(channels[0]).toBe(channels[1]);
  expect(channels[1]).toBe(channels[2]);

  await page.getByRole("link", { name: "Anotação", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Selecionar dataset", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "annotation-empty.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Perfis", exact: true }).click();
  await page.getByRole("button", { name: "Criar perfil", exact: true }).click();
  await page
    .getByLabel("Nome do perfil", { exact: true })
    .fill("Piso tolerante");
  const dialogBox = (await page.locator(".profile-dialog").boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(
    Math.abs(dialogBox.x + dialogBox.width / 2 - viewport.width / 2),
  ).toBeLessThan(8);
  expect(
    Math.abs(dialogBox.y + dialogBox.height / 2 - viewport.height / 2),
  ).toBeLessThan(8);
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "profile-form.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Salvar perfil", exact: true })
    .click();
  await page.getByRole("button", { name: "Criar perfil", exact: true }).click();
  await page.getByLabel("Nome do perfil", { exact: true }).fill("Piso regular");
  await page.getByLabel("Largura mínima", { exact: true }).selectOption("wide");
  await page
    .getByLabel("Tolerância ao piso", { exact: true })
    .selectOption("regular_only");
  await page
    .getByLabel("Desnível tolerado", { exact: true })
    .selectOption("none");
  await page.getByLabel("Aceita obstrução parcial", { exact: true }).uncheck();
  await page
    .getByRole("button", { name: "Salvar perfil", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Editar Piso tolerante", exact: true })
    .click();
  await page
    .getByLabel("Nome do perfil", { exact: true })
    .fill("Piso tolerante editado");
  await page
    .getByRole("button", { name: "Salvar perfil", exact: true })
    .click();
  await page.getByRole("button", { name: "Criar perfil", exact: true }).click();
  await page.getByLabel("Nome do perfil", { exact: true }).fill("Temporário");
  await page
    .getByRole("button", { name: "Salvar perfil", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Excluir Temporário", exact: true })
    .click();
  await expect(page.locator(".profile-card")).toHaveCount(2);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Entrar", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Usuário: " + process.env.WORKSPACE_TEST_USERNAME!),
  ).toBeVisible();
  await expect(page.locator(".profile-card")).toHaveCount(2);
  await expect(
    page.getByRole("heading", { name: "Piso tolerante editado", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "profiles.png"),
    fullPage: true,
  });
  await page.evaluate(() =>
    localStorage.setItem(
      "permear.profiles.v1",
      JSON.stringify({
        version: 1,
        profiles: [
          {
            id: "00000000-0000-4000-8000-000000000099",
            name: "Perfil local para migração",
            requirements: {
              minimum_passage_width: "adequate",
              surface_tolerance: "minor_problems",
              level_change_tolerance: "minor",
              accepts_partial_obstruction: true,
            },
          },
        ],
      }),
    ),
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Migrar perfis locais", exact: true })
    .click();
  await expect(page.locator(".profile-card")).toHaveCount(3);
  expect(
    await page.evaluate(() => localStorage.getItem("permear.profiles.v1")),
  ).toBeNull();
  await page
    .getByRole("button", {
      name: "Excluir Perfil local para migração",
      exact: true,
    })
    .click();
  await expect(page.locator(".profile-card")).toHaveCount(2);
  await page.getByRole("link", { name: "Demonstração", exact: true }).click();
  await expect(page.locator(".functional-fields")).toHaveCount(0);
  await page
    .getByLabel("Fotografia do trecho")
    .setInputFiles(process.env.WORKSPACE_TEST_IMAGE!);
  await page
    .getByLabel("Perfil 1", { exact: true })
    .selectOption({ label: "Piso tolerante editado" });
  await page
    .getByLabel("Perfil 2", { exact: true })
    .selectOption({ label: "Piso regular" });
  await page
    .getByLabel("Origem da observação", { exact: true })
    .fill("validacao_workspace_com_data_simulada");
  const localTime = (offsetHours: number) =>
    new Date(
      Date.now() -
        new Date().getTimezoneOffset() * 60000 -
        offsetHours * 3600000,
    )
      .toISOString()
      .slice(0, 16);
  await page
    .getByLabel("Data e hora da observação", { exact: true })
    .fill(localTime(0));
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "demonstration-form.png"),
    fullPage: true,
  });
  let saveAttempts = 0,
    modelCalls = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/transitability")) modelCalls++;
  });
  await page.route("**/analyses", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    saveAttempts++;
    if (saveAttempts <= 2)
      await route.fulfill({
        status: saveAttempts === 1 ? 503 : 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "test-only persistence failure" }),
      });
    else await route.continue();
  });
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().endsWith("/transitability") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Analisar", exact: true }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.assessments).toHaveLength(2);
  expect(result.assessments[0].profile.minimum_passage_width).toBe("adequate");
  expect(result.assessments[1].profile.minimum_passage_width).toBe("wide");
  expect(result.mask.data.length).toBeGreaterThan(100);
  expect(result.observation.is_valid).toBe(true);
  await expect(
    page.getByRole("tab", { name: "Avaliação", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".assessment")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Tentar salvar novamente", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Tentar salvar novamente", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Entrar", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Usuário", { exact: true })
    .fill(process.env.WORKSPACE_TEST_USERNAME!);
  await page
    .getByLabel("Senha", { exact: true })
    .fill(process.env.WORKSPACE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.locator(".assessment")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Tentar salvar novamente", exact: true })
    .click();
  expect(modelCalls).toBe(1);

  await expect(
    page.getByRole("button", { name: "Editar análise", exact: true }),
  ).toBeVisible();

  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "demonstration.png"),
    fullPage: true,
  });
  await writeFile(
    path.join(evidence, "real-response.json"),
    JSON.stringify(
      {
        ...result,
        mask: { ...result.mask, data: "<PNG omitido>" },
        timestamps_simulated: true,
      },
      null,
      2,
    ),
  );
  await page
    .getByRole("tab", { name: "Características e detalhes", exact: true })
    .click();
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "demonstration-details.png"),
    fullPage: true,
  });
  await expect(
    page.getByRole("button", { name: "Editar análise", exact: true }),
  ).toBeVisible();
  let inferenceRequests = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/transitability")) inferenceRequests++;
  });
  await page.getByRole("tab", { name: "Histórico", exact: true }).click();
  await expect(page.locator(".history-row")).toHaveCount(1);
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "history.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Abrir", exact: true }).click();
  await expect(page.locator(".assessment")).toHaveCount(2);
  await expect(page.locator(".result-images img")).toHaveCount(1);
  expect(inferenceRequests).toBe(0);
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "history-detail.png"),
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Análise", exact: true }).click();
  await page
    .getByRole("button", { name: "Editar análise", exact: true })
    .click();
  await page
    .getByLabel("Data e hora da observação", { exact: true })
    .fill(localTime(25));
  const expiredResponse = page.waitForResponse((r) =>
    r.url().endsWith("/transitability"),
  );
  await page.getByRole("button", { name: "Analisar", exact: true }).click();
  const expired = await (await expiredResponse).json();
  expect(expired.mask).toBeNull();
  expect(
    expired.assessments.map(
      (a: { classification: string }) => a.classification,
    ),
  ).toEqual(["undetermined", "undetermined"]);
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "expired-observation.png"),
    fullPage: true,
  });
  await expect(
    page.getByRole("button", { name: "Editar análise", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Histórico", exact: true }).click();
  await expect(page.locator(".history-row")).toHaveCount(2);
  await page
    .locator(".history-row")
    .first()
    .getByRole("button", { name: "Excluir", exact: true })
    .click();
  await expect(page.locator(".history-row")).toHaveCount(1);
  await page.getByRole("link", { name: "Dataset", exact: true }).click();
  await expect(page.getByLabel("Filtrar imagens")).toHaveCount(0);
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "dataset-empty.png"),
    fullPage: true,
  });
  await page
    .getByLabel("Importar pasta local")
    .setInputFiles(process.env.WORKSPACE_TEST_DATASET!);
  await expect(page.locator(".dataset-summary")).toContainText("1 imagem");
  await expect(page.locator(".dataset-summary")).toContainText("1 a revisar");
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "dataset.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Anotar", exact: false }).click();
  await expect(
    page.getByRole("heading", { name: "Anotação", exact: true }),
  ).toBeVisible();
  if (
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .count()
  )
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .click();
  await page
    .getByRole("radiogroup", { name: "Grau de obstrução", exact: true })
    .getByText("Total", { exact: true })
    .click();
  await page
    .getByLabel("Comentário", { exact: true })
    .fill('Validação do Workspace, "CSV" com vírgula.\nSegunda linha.');
  await page.getByRole("button", { name: "Desenhar", exact: true }).click();
  const editor = page.getByLabel("Editor da faixa de circulação");
  const box = (await editor.boundingBox())!;
  for (const [x, y] of [
    [0.1, 0.7],
    [0.3, 0.7],
    [0.2, 0.9],
  ])
    await page.mouse.click(box.x + box.width * x, box.y + box.height * y);
  await page
    .getByRole("button", { name: "Fechar polígono", exact: true })
    .click();
  await expect(page.locator(".polygon-frame polygon")).toHaveCount(2);
  await page.getByRole("button", { name: "Desfazer", exact: true }).click();
  await expect(page.locator(".polygon-frame polygon")).toHaveCount(1);
  await page.getByRole("button", { name: "Refazer", exact: true }).click();
  await expect(page.locator(".polygon-frame polygon")).toHaveCount(2);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "annotation.png"),
    fullPage: false,
  });
  await page
    .getByText("Revisão, histórico e proveniência", { exact: true })
    .click();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Exportar edição em CSV", exact: true })
    .click();
  const download = await downloadPromise;
  await download.saveAs(path.join(evidence, "exported_annotations.csv"));
  await expect(
    page.getByText("CSV exportado e progresso salvo neste navegador."),
  ).toBeVisible();
  // Real File System Access handles in isolated browser storage; only the native picker is substituted.
  await page.getByRole("link", { name: "Dataset", exact: true }).click();
  const csvSource = await readFile(
    path.join(
      process.env.WORKSPACE_TEST_DATASET!,
      "transitability_annotations.csv",
    ),
    "utf8",
  );
  const imageBase64 = (
    await readFile(process.env.WORKSPACE_TEST_IMAGE!)
  ).toString("base64");
  await page.evaluate(
    async ({ csvSource, imageBase64 }) => {
      const root = await navigator.storage.getDirectory();
      const directory = await root.getDirectoryHandle("workspace-validation", {
        create: true,
      });
      const images = await directory.getDirectoryHandle("images", {
        create: true,
      });
      const subset = await images.getDirectoryHandle("curb_ramp", {
        create: true,
      });
      const file = await subset.getFileHandle(
        "gsv-amsterdam-18384-CurbRamp.png",
        { create: true },
      );
      let stream = await file.createWritable();
      await stream.write(
        Uint8Array.from(atob(imageBase64), (c) => c.charCodeAt(0)),
      );
      await stream.close();
      const csv = await directory.getFileHandle(
        "transitability_annotations.csv",
        { create: true },
      );
      stream = await csv.createWritable();
      await stream.write(csvSource);
      await stream.close();
      Object.defineProperty(window, "showDirectoryPicker", {
        configurable: true,
        value: async () => directory,
      });
    },
    { csvSource, imageBase64 },
  );
  await page.getByText("Abrir dataset", { exact: true }).click();
  await page.getByRole("button", { name: "Abrir pasta local" }).click();
  await expect(page.locator(".dataset-summary")).toContainText(
    "workspace-validation",
  );
  await page.getByRole("button", { name: "Anotar", exact: false }).click();
  if (
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .count()
  )
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .click();
  await page
    .getByLabel("Comentário", { exact: true })
    .fill("Gravação direta validada no navegador.");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByText("Anotação salva no CSV local.")).toBeVisible();
  const savedCSV = await page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const d = await root.getDirectoryHandle("workspace-validation");
    return (
      await (await d.getFileHandle("transitability_annotations.csv")).getFile()
    ).text();
  });
  expect(savedCSV).toContain("Gravação direta validada no navegador.");
  await writeFile(path.join(evidence, "direct-write.csv"), savedCSV);
  if (
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .count()
  )
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .click();
  await page
    .getByText("Auxílio de segmentação pela API", { exact: true })
    .click();
  await page
    .getByLabel("Origem da observação", { exact: true })
    .fill("validacao_workspace_com_data_simulada");
  const simulatedDate = await page.evaluate(() =>
    new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16),
  );
  await page
    .getByLabel("Data da observação", { exact: true })
    .fill(simulatedDate);
  const suggestionResponse = page.waitForResponse((r) =>
    r.url().endsWith("/transitability"),
  );
  await page
    .getByRole("button", { name: "Gerar sugestão real", exact: true })
    .click();
  expect((await suggestionResponse).status()).toBe(200);
  await expect(
    page.getByRole("button", { name: "Restaurar sugestão", exact: true }),
  ).toBeVisible();
  expect(await page.locator(".polygon-frame polygon").count()).toBeGreaterThan(
    0,
  );
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Salvar", exact: true }),
  ).toBeVisible();
  const reviewedCSV = await page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const d = await root.getDirectoryHandle("workspace-validation");
    return (
      await (await d.getFileHandle("transitability_annotations.csv")).getFile()
    ).text();
  });
  expect(reviewedCSV).toContain("SegFormer common-dino-split");
  await writeFile(path.join(evidence, "suggestion-reviewed.csv"), reviewedCSV);

  if (
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .count()
  )
    await page
      .getByRole("button", { name: "Editar anotação", exact: true })
      .click();
  await page
    .getByRole("textbox", { name: "Comentário", exact: true })
    .fill(
      "Esta edição não deve sobrescrever um arquivo alterado externamente.",
    );
  await page.evaluate(async () => {
    const root = await navigator.storage.getDirectory();
    const d = await root.getDirectoryHandle("workspace-validation");
    const f = await d.getFileHandle("transitability_annotations.csv");
    const text = await (await f.getFile()).text();
    const stream = await f.createWritable();
    await stream.write(text + "\r\n");
    await stream.close();
  });
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "alterado fora do Workspace",
  );
  await page.getByRole("link", { name: "Início", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    animations: "disabled",
    path: path.join(evidence, "mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Abrir navegação" }).click();
  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Entrar", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("permear.session.v1")),
  ).toBeNull();
  await page
    .getByLabel("Usuário", { exact: true })
    .fill(process.env.WORKSPACE_TEST_USERNAME!);
  await page
    .getByLabel("Senha", { exact: true })
    .fill(process.env.WORKSPACE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Olá!", exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    const key = "permear.session.v1";
    const value = JSON.parse(sessionStorage.getItem(key)!);
    value.expiresAt = Date.now() - 1;
    sessionStorage.setItem(key, JSON.stringify(value));
  });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Entrar", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("permear.session.v1")),
  ).toBeNull();
  expect(errors).toEqual([]);
  await writeFile(
    path.join(evidence, "browser-checks.json"),
    JSON.stringify(
      {
        real_api: true,
        neutral_palette_verified: true,
        compact_login_card_verified: true,
        session_survives_reload: true,
        expired_session_rejected: true,
        explicit_legacy_migration: true,
        save_failure_keeps_result: true,
        save_retry_without_inference: true,
        supabase_http_test_double: true,
        remote_supabase_validated: false,
        history_without_inference: true,
        analysis_files_recovered: true,
        analysis_deleted: true,
        profiles_created_edited_deleted: true,
        profiles_persisted_after_reload: true,
        registered_profile_selection: true,
        paired_profiles: true,
        expired_observation: true,
        annotation_csv_export: true,
        manual_polygon_edit: true,
        undo_redo: true,
        file_system_access_write: true,
        real_segmentation_suggestion: true,
        external_change_blocked: true,
        logout: true,
        browser_errors: errors,
      },
      null,
      2,
    ),
  );
});
