import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin, Connect } from "vite";
import type { IncomingMessage, ServerResponse } from "node:http";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(Buffer.from(c)));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function timeStamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_` +
    `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
  );
}

function sanitizeModName(raw: string): string {
  const s = String(raw || "")
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return s || `mission_squad_${timeStamp()}`;
}

function uniqueModName(base: string): string {
  let name = sanitizeModName(base);
  let outDir = path.join(REPO_ROOT, "Mods", name);
  if (!fs.existsSync(outDir)) return name;
  name = `${name}_${timeStamp()}`;
  outDir = path.join(REPO_ROOT, "Mods", name);
  let n = 2;
  while (fs.existsSync(outDir)) {
    name = `${sanitizeModName(base)}_${timeStamp()}_${n}`;
    outDir = path.join(REPO_ROOT, "Mods", name);
    n += 1;
  }
  return name;
}

function runPython(
  args: string[]
): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn("python", args, { cwd: REPO_ROOT });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => {
      stdout += String(d);
    });
    child.stderr.on("data", (d) => {
      stderr += String(d);
    });
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}

function jsonOk(res: ServerResponse, body: unknown) {
  res.statusCode = 200;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

function jsonErr(res: ServerResponse, code: number, error: string) {
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify({ error }));
}

/** Local hub at `/`, editor SPA under `/editor/`, zip downloads. Pages build ignores this. */
function uoHubDevPlugin(): Plugin {
  const siteDir = path.resolve(REPO_ROOT, "Tools/site");
  const levelZip = path.resolve(REPO_ROOT, "Release/enemy_level_scale.zip");
  const xpZipDir = path.resolve(REPO_ROOT, "Release/xp_scale");

  return {
    name: "uo-hub-dev",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url || "").split("?")[0];

        if (url === "/hub.css" || url === "/hub.js") {
          const file = url === "/hub.css" ? "hub.css" : "hub.js";
          res.setHeader(
            "Content-Type",
            file.endsWith(".css")
              ? "text/css; charset=utf-8"
              : "text/javascript; charset=utf-8"
          );
          res.end(fs.readFileSync(path.join(siteDir, file)));
          return;
        }
        if (url === "/enemy_level_scale.zip") {
          if (!fs.existsSync(levelZip)) {
            res.statusCode = 404;
            res.end("enemy_level_scale.zip missing — build Release/ first");
            return;
          }
          res.setHeader("Content-Type", "application/zip");
          res.setHeader(
            "Content-Disposition",
            'attachment; filename="enemy_level_scale.zip"'
          );
          fs.createReadStream(levelZip).pipe(res);
          return;
        }
        if (url.startsWith("/xp_scale/") && url.endsWith(".zip")) {
          const name = path.basename(url);
          const zipPath = path.join(xpZipDir, name);
          if (!fs.existsSync(zipPath) || !name.startsWith("xp_scale_")) {
            res.statusCode = 404;
            res.end("xp scale zip not found");
            return;
          }
          res.setHeader("Content-Type", "application/zip");
          res.setHeader(
            "Content-Disposition",
            `attachment; filename="${name}"`
          );
          fs.createReadStream(zipPath).pipe(res);
          return;
        }
        if (url === "/" || url === "/index.html") {
          res.setHeader("Content-Type", "text/html; charset=utf-8");
          res.end(fs.readFileSync(path.join(siteDir, "index.html")));
          return;
        }
        // Mount the Vite SPA under /editor/ (same paths as GitHub Pages).
        if (url === "/editor" || url === "/editor/") {
          req.url = "/index.html";
          next();
          return;
        }
        if (url.startsWith("/editor/")) {
          req.url = url.slice("/editor".length) || "/";
          next();
          return;
        }
        next();
      });
    },
  };
}

function missionEditorApiPlugin(): Plugin {
  return {
    name: "mission-editor-api",
    configureServer(server) {
      server.middlewares.use(
        async (
          req: Connect.IncomingMessage,
          res: ServerResponse,
          next: Connect.NextFunction
        ) => {
          const url = req.url || "";

          if (url === "/api/resolve-tactics" && req.method === "POST") {
            try {
              const raw = await readBody(req);
              const body = JSON.parse(raw || "{}") as {
                patches?: Array<string | { path?: string; name?: string; text?: string }>;
              };
              const patches = Array.isArray(body.patches) ? body.patches : [];
              const script = path.join(
                REPO_ROOT,
                "Scripts/resolve_tactics_mods.py"
              );
              // Large payloads via temp file — avoids Windows command-line limits.
              const tmpDir = path.join(REPO_ROOT, "Extraction/editor/exports");
              fs.mkdirSync(tmpDir, { recursive: true });
              const tmpJson = path.join(
                tmpDir,
                `_resolve_tactics_${Date.now()}.json`
              );
              fs.writeFileSync(
                tmpJson,
                JSON.stringify({ patches }),
                "utf8"
              );
              const result = await runPython([
                script,
                "--json-file",
                tmpJson,
              ]);
              try {
                fs.unlinkSync(tmpJson);
              } catch {
                /* ignore */
              }
              if (result.code !== 0) {
                jsonErr(
                  res,
                  500,
                  result.stderr || result.stdout || "resolve failed"
                );
                return;
              }
              const payload = JSON.parse(result.stdout);
              jsonOk(res, payload);
            } catch (e) {
              jsonErr(res, 500, String(e));
            }
            return;
          }

          if (url !== "/api/export-mod" || req.method !== "POST") {
            next();
            return;
          }
          try {
            const raw = await readBody(req);
            const body = JSON.parse(raw || "{}") as {
              edits?: unknown;
              mod_name?: string;
              unique?: boolean;
            };
            const edits = body.edits;
            if (!edits || typeof edits !== "object") {
              jsonErr(res, 400, "missing edits");
              return;
            }

            const modName =
              body.unique === false
                ? sanitizeModName(body.mod_name || "mission_squad_editor")
                : uniqueModName(
                    body.mod_name || `mission_squad_${timeStamp()}`
                  );

            const editsDir = path.join(REPO_ROOT, "Extraction/editor/exports");
            fs.mkdirSync(editsDir, { recursive: true });
            const editsPath = path.join(
              editsDir,
              `mission_edits_${modName}.json`
            );
            fs.writeFileSync(
              editsPath,
              JSON.stringify(edits, null, 2) + "\n",
              "utf8"
            );
            fs.writeFileSync(
              path.join(REPO_ROOT, "Extraction/editor/mission_edits.json"),
              JSON.stringify(edits, null, 2) + "\n",
              "utf8"
            );

            const script = path.join(REPO_ROOT, "Scripts/export_mission_mod.py");
            const outDir = path.join(REPO_ROOT, "Mods", modName);
            const result = await runPython([
              script,
              "--mod-name",
              modName,
              "--edits",
              editsPath,
            ]);

            if (result.code !== 0) {
              jsonErr(
                res,
                500,
                result.stderr || result.stdout || "export failed"
              );
              return;
            }

            const patchMatch = result.stdout.match(/\((\d+) patches\)/);
            jsonOk(res, {
              ok: true,
              mod_name: modName,
              out_dir: outDir,
              edits_path: editsPath,
              path: path.join(outDir, "exefs", "main.pchtxt"),
              patches: patchMatch ? Number(patchMatch[1]) : undefined,
              log: result.stdout.trim(),
            });
          } catch (e) {
            jsonErr(res, 500, String(e));
          }
        }
      );
    },
  };
}

export default defineConfig({
  // Local: `/` hub + `/editor/` SPA (middleware). Pages sets VITE_BASE=/UOSquadEditor/editor/.
  base: process.env.VITE_BASE || "/",
  plugins: [react(), uoHubDevPlugin(), missionEditorApiPlugin()],
  server: {
    open: "/",
  },
});
