import { execFile } from 'node:child_process'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { promisify } from 'node:util'

const exec = promisify(execFile)
const pages = [
  'README.md',
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
  'docs/guides/testing.md',
]

function importedExample(markdown, language, file) {
  const fence = '```'
  const pattern = new RegExp(`${fence}${language}\\n([\\s\\S]*?)${fence}`, 'g')
  const blocks = [...markdown.matchAll(pattern)]
    .map((match) => match[1])
    .filter((code) => /from ['"]sley['"]|from sley import/.test(code))

  if (blocks.length === 0) throw new Error(`${file}: missing complete ${language} example`)
  return blocks[0]
}

const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'sley-docs-'))
const typescriptFiles = []

try {
  for (const [index, file] of pages.entries()) {
    const markdown = await fs.readFile(file, 'utf8')
    const python = path.join(temporary, `${index}.py`)
    const typescript = path.resolve('typescript', `.docs-example-${index}.mts`)

    await fs.writeFile(python, importedExample(markdown, 'python', file))
    await fs.writeFile(typescript, importedExample(markdown, 'typescript', file))
    typescriptFiles.push(typescript)

    await exec('python', [python], {
      env: { ...process.env, PYTHONPATH: path.resolve('python') },
    })
    await exec('node', [typescript])
  }

  await exec('pnpm', [
    '--dir',
    'typescript',
    'exec',
    'tsc',
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

console.log(`Ran ${pages.length * 2} documentation examples.`)
