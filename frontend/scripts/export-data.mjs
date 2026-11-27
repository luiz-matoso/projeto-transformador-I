import { spawnSync } from "node:child_process";
const result = spawnSync(
  process.env.PYTHON || "python",
  ["-m", "scripts.export_workspace_data"],
  { cwd: new URL("../../", import.meta.url), stdio: "inherit" },
);
process.exit(result.status ?? 1);
