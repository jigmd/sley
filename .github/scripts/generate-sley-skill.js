/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 *
 * Copyright (c) 2026, Victor Duarte (zvictor)
 */
import fs from 'node:fs/promises'
import path from 'node:path/posix'

const sourceDirectories = ['docs/reference', 'docs/guides']
const skillDirectory = 'skills/sley'
const sources = (
  await Promise.all(
    sourceDirectories.map(async (directory) =>
      (await fs.readdir(directory)).filter((name) => name.endsWith('.md')).map((name) => path.join(directory, name)),
    ),
  )
)
  .flat()
  .sort()
const copies = new Map(sources.map((source) => [source, path.join(skillDirectory, path.relative('docs', source))]))

function validateLinks(markdown, source) {
  for (const [, link] of markdown.matchAll(/\]\(([^)]+)\)/g)) {
    if (link.startsWith('#')) continue
    if (/^[a-z]+:/i.test(link)) throw new Error(`${source}: external reference ${link}`)

    const [pathname] = link.split('#')
    const sourcePath = path.normalize(path.join(path.dirname(source), pathname))
    if (!copies.has(sourcePath)) throw new Error(`${source}: uncopied reference ${link}`)
  }
}

for (const directory of sourceDirectories) {
  await fs.rm(path.join(skillDirectory, path.basename(directory)), { recursive: true, force: true })
}
for (const [source, target] of copies) {
  const markdown = await fs.readFile(source, 'utf8')
  validateLinks(markdown, source)
  await fs.mkdir(path.dirname(target), { recursive: true })
  await fs.writeFile(target, markdown)
}

console.log(`Generated ${copies.size} Sley skill references.`)
