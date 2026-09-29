// ESLint flat config for the card: the core JS recommended rules plus the
// typescript-eslint recommended set. Syntax-only (no type-aware rules) so the
// lint stays fast; `npm run typecheck` covers the type side, which is also why
// `no-undef` is off for .ts files (typescript-eslint's eslint-recommended).
import js from '@eslint/js';
import tsPlugin from '@typescript-eslint/eslint-plugin';

export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**'] },
  js.configs.recommended,
  ...tsPlugin.configs['flat/recommended'],
  {
    // Node-side tooling (this file, rollup.config.mjs, scripts/*.mjs).
    files: ['**/*.{js,mjs}'],
    languageOptions: { globals: { process: 'readonly', console: 'readonly', URL: 'readonly' } },
  },
  {
    files: ['src/**/*.ts', 'tests/**/*.ts'],
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
];
