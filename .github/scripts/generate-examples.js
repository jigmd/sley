/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 *
 * Copyright (c) 2025, Victor Duarte (zvictor)
 */
import fs from 'node:fs/promises'

const REPOSITORY = 'https://github.com/jigmd/sley'
const START = '<!-- generated-project-details:start -->'
const END = '<!-- generated-project-details:end -->'

async function readProject(directory) {
  const readme = await fs.readFile(`cookbook/${directory}/README.md`, 'utf8')
  const frontmatter = readme.match(/^---\s*\n([\s\S]*?)\n---\s*\n/)
  if (!frontmatter) throw new Error(`${directory}: missing README frontmatter`)

  const complexity = frontmatter[1].match(/^complexity:\s*([\d.]+)\s*$/m)
  if (!complexity) throw new Error(`${directory}: missing complexity`)
  const complexityValue = Number(complexity[1])
  if (!Number.isFinite(complexityValue)) throw new Error(`${directory}: invalid complexity`)

  const lesson = readme.slice(frontmatter[0].length).trim()
  const heading = lesson.match(/^# (.+?)(?:\r?\n|$)/)
  if (!heading) throw new Error(`${directory}: README must start with an H1`)

  return {
    complexity: complexityValue,
    directory,
    lesson: lesson.slice(heading[0].length).trim(),
    title: heading[1],
  }
}

async function readProjects(prefix) {
  const entries = await fs.readdir('cookbook', { withFileTypes: true })
  const directories = entries.filter((entry) => entry.isDirectory() && entry.name.startsWith(`${prefix}-`)).map((entry) => entry.name)

  const projects = await Promise.all(directories.map(readProject))
  return projects.sort((left, right) => left.complexity - right.complexity || left.directory.localeCompare(right.directory))
}

function render(projects) {
  return projects
    .map(
      ({ complexity, directory, lesson, title }) => `### ${title} ([${directory}](${REPOSITORY}/tree/main/cookbook/${directory}))

**Complexity:** ${complexity}

<details>
<summary>Read the full lesson</summary>

${lesson}

</details>`,
    )
    .join('\n\n')
}

async function updateCatalog(file, projects) {
  const catalog = await fs.readFile(file, 'utf8')
  const start = catalog.indexOf(START)
  const end = catalog.indexOf(END)
  if (start < 0 || end < start) throw new Error(`${file}: missing generated-section markers`)

  const generated = render(projects)
  const updated = `${catalog.slice(0, start + START.length)}\n\n${generated}\n\n${catalog.slice(end)}`
  if (updated !== catalog) await fs.writeFile(file, updated)
}

const python = await readProjects('python')
const typescript = await readProjects('typescript')

await updateCatalog('docs/cookbook/python.md', python)
await updateCatalog('docs/cookbook/typescript.md', typescript)
console.log(`Generated lessons for ${python.length} Python and ${typescript.length} TypeScript projects.`)
