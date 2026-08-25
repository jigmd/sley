/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 *
 * Copyright (c) 2025, Victor Duarte (zvictor)
 */
import fs from 'node:fs/promises'
import prettier from 'prettier'

const REPOSITORY = 'https://github.com/jigmd/sley'
const catalog = JSON.parse(await fs.readFile('docs/examples/catalog.json', 'utf8'))

async function readProject(directory) {
  const readme = await fs.readFile(`cookbook/${directory}/README.md`, 'utf8')
  const frontmatter = readme.match(/^---\s*\n([\s\S]*?)\n---\s*\n/)
  if (!frontmatter) throw new Error(`${directory}: missing README frontmatter`)

  const rawComplexity = frontmatter[1].match(/^complexity:\s*([\d.]+)\s*$/m)?.[1]
  const complexity = Number(rawComplexity)
  if (!rawComplexity || !Number.isFinite(complexity)) throw new Error(`${directory}: invalid complexity`)

  const lesson = readme.slice(frontmatter[0].length).trim()
  const title = lesson.match(/^# (.+?)(?:\r?\n|$)/)?.[1]
  if (!title) throw new Error(`${directory}: README must start with an H1`)

  return { complexity, title }
}

async function projectDirectories(prefix) {
  const entries = await fs.readdir('cookbook', { withFileTypes: true })
  return entries.filter((entry) => entry.isDirectory() && entry.name.startsWith(`${prefix}-`)).map((entry) => entry.name)
}

function renderEntry(entry, project) {
  const code = `${REPOSITORY}/tree/main/cookbook/${entry.project}`
  const lesson = `${REPOSITORY}/blob/main/cookbook/${entry.project}/README.md`
  return `| [${project.title}](${code})<br>[Read the lesson](${lesson}) | ${entry.lesson} | ${entry.mechanisms.map((item) => `\`${item}\``).join(', ')} | ${project.complexity} |`
}

async function renderLanguage(language, groups) {
  const configured = groups.flatMap((group) => group.projects.map((entry) => entry.project))
  const discovered = await projectDirectories(language)
  const missing = discovered.filter((directory) => !configured.includes(directory))
  const stale = configured.filter((directory) => !discovered.includes(directory))
  if (missing.length || stale.length || new Set(configured).size !== configured.length) {
    throw new Error(`${language}: catalog mismatch; missing=${missing.join(',')} stale=${stale.join(',')}`)
  }

  const details = new Map(await Promise.all(configured.map(async (directory) => [directory, await readProject(directory)])))
  return groups
    .map(
      (group) => `## ${group.name}

| Project | What it teaches | Sley mechanisms | Complexity |
| --- | --- | --- | ---: |
${group.projects.map((entry) => renderEntry(entry, details.get(entry.project))).join('\n')}`,
    )
    .join('\n\n')
}

async function generate(language, title, description) {
  const groups = catalog[language]
  if (!Array.isArray(groups)) throw new Error(`${language}: missing catalog groups`)
  const body = await renderLanguage(language, groups)
  const output = `---
description: ${description}
---

# ${title}

Do not choose by ambition. Choose the smallest project that answers your next
question, run it, and change one behavior. Complexity estimates cognitive load,
not quality; lower is usually the more useful starting point.

${body}
`
  const file = `docs/examples/${language}.md`
  await fs.writeFile(file, await prettier.format(output, { filepath: file }))
}

await generate(
  'python',
  'Python Examples',
  'Browse complete Python projects by learning goal, Sley mechanism, and cognitive complexity.',
)
await generate(
  'typescript',
  'TypeScript Examples',
  'Browse complete TypeScript projects by learning goal, Sley mechanism, and cognitive complexity.',
)

console.log('Generated catalogs for 37 Python and 4 TypeScript projects.')
