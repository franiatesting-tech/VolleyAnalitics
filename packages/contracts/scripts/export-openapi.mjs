// Exports services/api's OpenAPI schema to packages/contracts/openapi.json by
// shelling out to the same Python env the API runs in (via `uv run`) --
// there is exactly one place the schema is defined (the FastAPI app /
// Pydantic schemas), this script never hand-encodes any of it.
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..", "..");
const apiDir = join(repoRoot, "services", "api");
const outFile = join(__dirname, "..", "openapi.json");

const pythonCode = `
from volley_api.main import app
import json
print(json.dumps(app.openapi()))
`;

// Placeholder env values: exporting the schema only needs the app to
// *import*, not to actually connect to anything -- see Settings' required
// fields in volley_api/core/config.py.
const env = {
  ...process.env,
  DATABASE_URL: process.env.DATABASE_URL ?? "postgresql://u:p@h/d",
  VALKEY_URL: process.env.VALKEY_URL ?? "redis://h:6379/0",
  AUTH_JWKS_URL: process.env.AUTH_JWKS_URL ?? "http://h/jwks",
  AUTH_ISSUER: process.env.AUTH_ISSUER ?? "http://h",
  AUTH_AUDIENCE: process.env.AUTH_AUDIENCE ?? "aud",
};

const result = spawnSync(
  "uv",
  ["run", "--project", "..", "--package", "volley-api", "python", "-c", pythonCode],
  { cwd: apiDir, env, encoding: "utf-8" }
);

if (result.status !== 0) {
  console.error(result.stderr);
  process.exit(result.status ?? 1);
}

const schema = JSON.parse(result.stdout);
writeFileSync(outFile, JSON.stringify(schema, null, 2) + "\n");
console.log(`Wrote ${outFile}`);
