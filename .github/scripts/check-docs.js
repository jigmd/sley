import fs from 'node:fs/promises'
import path from 'node:path'

const DOCS = 'docs'
const SUMMARY = path.join(DOCS, 'SUMMARY.md')
const docsRoot = path.resolve(DOCS)

function insideDocs(target) {
  return target === docsRoot || target.startsWith(`${docsRoot}${path.sep}`)
}

async function markdownFiles(directory) {
  const entries = await fs.readdir(directory, { withFileTypes: true })
  const files = await Promise.all(
    entries.map((entry) => {
      const target = path.join(directory, entry.name)
      return entry.isDirectory() ? markdownFiles(target) : [target]
    }),
  )
  return files.flat().filter((file) => file.endsWith('.md') && !file.endsWith('AGENTS.md'))
}

function localLinks(markdown) {
  const prose = markdown.replace(/```[\s\S]*?```/g, '')
  return [...prose.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)].map((match) => match[1])
}

function pageDescription(markdown, file) {
  const frontmatter = markdown.match(/^---\n([\s\S]*?)\n---\n/)
  if (!frontmatter) throw new Error(`${file}: missing frontmatter`)
  const description = frontmatter[1].match(/^description:\s*(.+)$/m)?.[1]?.trim()
  if (!description) throw new Error(`${file}: missing description`)
  if (description.length > 200) throw new Error(`${file}: description exceeds 200 characters`)
}

const summary = await fs.readFile(SUMMARY, 'utf8')
const listed = localLinks(summary).map((link) => path.normalize(path.join(DOCS, link)))
const pages = (await markdownFiles(DOCS)).filter((file) => file !== SUMMARY)

for (const page of pages) {
  const markdown = await fs.readFile(page, 'utf8')
  pageDescription(markdown, page)
  const prose = markdown.replace(/```[\s\S]*?```/g, '')
  if ((prose.match(/^# /gm) ?? []).length !== 1) throw new Error(`${page}: expected one H1`)
  if (markdown.includes('machine-display:')) throw new Error(`${page}: obsolete machine-display frontmatter`)
  if (!listed.includes(page)) throw new Error(`${page}: page is missing from SUMMARY.md`)

  for (const link of localLinks(markdown)) {
    if (/^(?:[a-z]+:|#)/i.test(link)) continue
    const target = decodeURIComponent(link.split('#', 1)[0])
    if (!target) continue
    const resolved = path.resolve(path.dirname(page), target)
    if (!insideDocs(resolved)) throw new Error(`${page}: local link escapes published docs: ${link}`)
    try {
      await fs.access(resolved)
    } catch {
      throw new Error(`${page}: broken local link ${link}`)
    }
  }
}

for (const page of listed) {
  if (!pages.includes(page)) throw new Error(`SUMMARY.md: missing page ${page}`)
}

if (new Set(listed).size !== listed.length) throw new Error('SUMMARY.md: duplicate page')
const gitbook = await fs.readFile('.gitbook.yaml', 'utf8')
const redirects = gitbook.match(/^redirects:\n([\s\S]+)$/m)?.[1]
if (!redirects) throw new Error('.gitbook.yaml: missing redirects')

for (const match of redirects.matchAll(/^  [^:\n]+:\s+([^\s]+)\s*$/gm)) {
  const [target, fragment] = match[1].split('#', 2)
  const resolved = path.resolve(DOCS, target)
  if (!insideDocs(resolved)) throw new Error(`.gitbook.yaml: redirect escapes published docs: ${match[1]}`)

  const markdown = await fs.readFile(resolved, 'utf8')
  if (fragment) {
    const slugs = [...markdown.matchAll(/^#{1,6}\s+(.+)$/gm)].map((heading) =>
      heading[1]
        .replace(/`/g, '')
        .toLowerCase()
        .replace(/[^\p{L}\p{N}\s-]/gu, '')
        .trim()
        .replace(/\s+/g, '-'),
    )
    if (!slugs.includes(fragment)) throw new Error(`.gitbook.yaml: missing redirect anchor ${match[1]}`)
  }
}

try {
  await fs.access('.gitbook.yml')
  throw new Error('use .gitbook.yaml, not the legacy .gitbook.yml')
} catch (error) {
  if (error.code !== 'ENOENT') throw error
}

const pythonFacade = await fs.readFile('python/sley/__init__.py', 'utf8')
const pythonExports = [...pythonFacade.match(/__all__ = \(([\s\S]*?)\)/)[1].matchAll(/"([^"]+)"/g)].map((match) => match[1])
const pythonReference = await fs.readFile('docs/reference/python.md', 'utf8')
for (const symbol of pythonExports) {
  if (!pythonReference.includes(`\`${symbol}\``)) throw new Error(`Python reference: missing ${symbol}`)
}

const typescriptFacade = await fs.readFile('typescript/sley.ts', 'utf8')
const exportBlocks = [...typescriptFacade.matchAll(/export\s+(?:type\s+)?\{([\s\S]*?)\}/g)]
const typescriptExports = exportBlocks.flatMap((block) =>
  block[1]
    .split(',')
    .map((item) =>
      item
        .trim()
        .replace(/^type\s+/, '')
        .split(/\s+as\s+/)
        .at(-1),
    )
    .filter(Boolean),
)
const typescriptReference = await fs.readFile('docs/reference/typescript.md', 'utf8')
for (const symbol of typescriptExports) {
  if (!typescriptReference.includes(`\`${symbol}\``)) throw new Error(`TypeScript reference: missing ${symbol}`)
}

console.log(`Checked ${pages.length} documentation pages.`)
