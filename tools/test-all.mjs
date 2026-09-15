/* Run every tools/test-*.mjs in turn and say which ones failed.
 *   npm test
 * Sequential on purpose: the DOM tests each bind their own port and drive one
 * Chrome, and two of them tune into the live tower. Each test's own output
 * streams through; the summary at the end is the part worth reading.
 */
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const TOOLS = dirname(fileURLToPath(import.meta.url));
const SELF = "test-all.mjs";
const TEST = /^test-.*\.mjs$/;

const tests = readdirSync(TOOLS).filter((f) => TEST.test(f) && f !== SELF).sort();
const failed = [];

for (const t of tests) {
  console.log(`\n══ ${t}`);
  const r = spawnSync(process.execPath, [join(TOOLS, t)], { stdio: "inherit" });
  if (r.status !== 0) {
    failed.push(t);
  }
}

console.log(`\n${tests.length - failed.length}/${tests.length} suites passed`);
for (const t of failed) {
  console.log(`  FAILED  ${t}`);
}
process.exit(failed.length === 0 ? 0 : 1);
