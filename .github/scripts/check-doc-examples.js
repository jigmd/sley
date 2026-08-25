import { execFile } from 'node:child_process'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { promisify } from 'node:util'

const exec = promisify(execFile)
const pages = [
  'README.md',
  'docs/README.md',
  'docs/quickstart.md',
  'docs/learn/routing.md',
  'docs/learn/data.md',
  'docs/learn/fan-out-and-combine.md',
  'docs/learn/nested-flows.md',
  'docs/learn/failures-and-results.md',
  'docs/guides/validation-and-types.md',
  'docs/guides/concurrency-and-cycles.md',
  'docs/guides/retry-and-recovery.md',
  'docs/guides/inspection.md',
  'docs/guides/integration-boundaries.md',
  'docs/guides/testing.md',
]

function importedExamples(markdown, language, file) {
  const fence = '```'
  const pattern = new RegExp(`${fence}${language}\\n([\\s\\S]*?)${fence}`, 'g')
  const blocks = [...markdown.matchAll(pattern)]
    .map((match) => match[1])
    .filter((code) => /from ['"]@jigging\/sley['"]|from sley import/.test(code))

  if (blocks.length === 0) throw new Error(`${file}: missing complete ${language} example`)
  return blocks
}

const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'sley-docs-'))
const typescriptFiles = []
let exampleCount = 0

try {
  for (const [index, file] of pages.entries()) {
    const markdown = await fs.readFile(file, 'utf8')
    const pythonExamples = importedExamples(markdown, 'python', file)
    const typescriptExamples = importedExamples(markdown, 'typescript', file)

    for (const [exampleIndex, code] of pythonExamples.entries()) {
      const python = path.join(temporary, `${index}-${exampleIndex}.py`)
      await fs.writeFile(python, code)
      await exec('python', [python], {
        env: { ...process.env, PYTHONPATH: path.resolve('python') },
      })
      exampleCount++
    }

    for (const [exampleIndex, code] of typescriptExamples.entries()) {
      const typescript = path.resolve('typescript', `.docs-example-${index}-${exampleIndex}.mts`)
      await fs.writeFile(typescript, code)
      typescriptFiles.push(typescript)
      await exec('node', [typescript])
      exampleCount++
    }
  }

  await exec(path.resolve('node_modules/.bin/tsc'), [
    '--noEmit',
    '--strict',
    '--target',
    'ES2024',
    '--module',
    'NodeNext',
    '--moduleResolution',
    'NodeNext',
    '--skipLibCheck',
    ...typescriptFiles,
  ])
} finally {
  await Promise.all(typescriptFiles.map((file) => fs.rm(file, { force: true })))
  await fs.rm(temporary, { recursive: true, force: true })
}

console.log(`Ran ${exampleCount} complete documentation examples.`)
