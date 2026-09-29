#!/usr/bin/env node
// Fail when the committed card bundle is stale.
//
// Rebuilds the card into a throwaway directory with the same rollup config
// that `npm run build` uses, then compares the output file by file with the
// bundle committed at custom_components/adaptive_cover/www/. CI runs this so a
// card source change cannot ship without its rebuilt bundle (and the bundle
// cannot be hand-edited). Fix a failure with `npm run build` and commit www/.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const cardDir = fileURLToPath(new URL('..', import.meta.url));
const wwwDir = fileURLToPath(
  new URL('../../custom_components/adaptive_cover/www/', import.meta.url),
);
const rollupBin = join(cardDir, 'node_modules', 'rollup', 'dist', 'bin', 'rollup');

const outDir = mkdtempSync(join(tmpdir(), 'adaptive-cover-card-'));
const problems = [];
try {
  const env = { ...process.env, CARD_OUT_DIR: outDir };
  delete env.ROLLUP_WATCH;
  const build = spawnSync(process.execPath, [rollupBin, '-c'], {
    cwd: cardDir,
    env,
    stdio: 'inherit',
  });
  if (build.status !== 0) {
    console.error('check-bundle: the card build failed');
    process.exit(build.status ?? 1);
  }

  const built = readdirSync(outDir).sort();
  const committed = readdirSync(wwwDir)
    .filter((name) => !name.startsWith('.'))
    .sort();
  for (const name of [...new Set([...built, ...committed])].sort()) {
    if (!committed.includes(name)) {
      problems.push(`${name}: produced by the build but not committed in www/`);
    } else if (!built.includes(name)) {
      problems.push(`${name}: committed in www/ but not produced by the build`);
    } else {
      const fresh = readFileSync(join(outDir, name));
      const shipped = readFileSync(join(wwwDir, name));
      if (!fresh.equals(shipped)) {
        problems.push(
          `${name}: differs from a fresh build (${shipped.length} bytes committed, ${fresh.length} bytes built)`,
        );
      }
    }
  }
} finally {
  rmSync(outDir, { recursive: true, force: true });
}

if (problems.length > 0) {
  console.error('check-bundle: custom_components/adaptive_cover/www/ is out of date:');
  for (const p of problems) console.error(`  - ${p}`);
  console.error('Run `npm run build` in card/ and commit custom_components/adaptive_cover/www/.');
  process.exit(1);
}
console.log('check-bundle: custom_components/adaptive_cover/www/ matches a fresh build');
