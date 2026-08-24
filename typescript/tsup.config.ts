import type { Options } from 'tsup'

export const tsup: Options = {
  clean: true,
  dts: true,
  format: ['cjs', 'esm'],
  minify: true,
  bundle: true,
  entryPoints: ['sley.ts'],
  outDir: 'dist',
}
