import type { Options } from 'tsup'

export const tsup: Options = {
  clean: true,
  dts: true,
  format: ['cjs', 'esm'],
  minify: true,
  bundle: true,
  target: 'es2022',
  entryPoints: ['sley.ts'],
  outDir: 'dist',
}
