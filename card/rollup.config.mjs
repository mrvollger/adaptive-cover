import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import typescript from '@rollup/plugin-typescript';
import terser from '@rollup/plugin-terser';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const pkg = JSON.parse(readFileSync('./package.json', 'utf8'));
const dev = process.env.ROLLUP_WATCH === 'true';

// The shipped bundle lives inside the integration, which serves and registers
// it (custom_components/adaptive_cover/frontend.py), so `npm run build` writes
// straight there and the result is committed. Watch mode (`npm run dev`) writes
// dist/ instead so sourcemaps never land in www/. CARD_OUT_DIR overrides both:
// `npm run check-bundle` builds into a temp dir and diffs it against www/.
const WWW_DIR = fileURLToPath(new URL('../custom_components/adaptive_cover/www/', import.meta.url));
const outDir = process.env.CARD_OUT_DIR || (dev ? 'dist' : WWW_DIR);

export default {
  input: 'src/adaptive-cover-card.ts',
  output: {
    file: join(outDir, 'adaptive-cover-card.js'),
    format: 'es',
    sourcemap: dev,
    banner: `/*! adaptive-cover-card v${pkg.version} | MIT License | https://github.com/mrvollger/adaptive-cover-card */`,
  },
  // @formatjs/intl-utils (pulled in by custom-card-helpers) ships UMD with
  // top-level `this`; rollup rewrites it to `undefined` and warns. Declare the
  // module context as `window` so the TS `__extends`/`__assign` helpers resolve
  // correctly and the warning goes away.
  moduleContext: (id) => (id.includes('@formatjs/intl-utils') ? 'window' : undefined),
  plugins: [
    resolve({ browser: true }),
    commonjs(),
    typescript({ tsconfig: './tsconfig.json', sourceMap: dev, inlineSources: dev }),
    !dev &&
      terser({
        format: { comments: /^!/ },
        compress: { passes: 2 },
      }),
  ].filter(Boolean),
};
