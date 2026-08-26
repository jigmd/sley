/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 *
 * Copyright (c) 2026, Victor Duarte (zvictor)
 */
import fs from 'node:fs/promises'
import path from 'node:path/posix'

const SITE = 'https://sley.jig.md'
const copies = new Map([
  ['docs/quickstart.md', 'skills/sley/references/quickstart.md'],
  ['docs/reference/python.md', 'skills/sley/references/python.md'],
  ['docs/reference/typescript.md', 'skills/sley/references/typescript.md'],
  ['docs/reference/runtime-semantics.md', 'skills/sley/references/runtime-semantics.md'],
])

function portableLinks(markdown, source, target) {
  return markdown.replace(/\]\(([^)]+)\)/g, (match, link) => {
    if (/^(?:[a-z]+:|#)/i.test(link)) return match

    const [pathname, fragment] = link.split('#', 2)
    const sourcePath = path.normalize(path.join(path.dirname(source), pathname))
    const copiedPath = copies.get(sourcePath)
    const portablePath = copiedPath
      ? path.relative(path.dirname(target), copiedPath)
      : `${SITE}/${sourcePath.replace(/^docs\//, '').replace(/\.md$/, '')}`

    return `](${portablePath}${fragment ? `#${fragment}` : ''})`
  })
}

await fs.mkdir('skills/sley/references', { recursive: true })
for (const [source, target] of copies) {
  const markdown = await fs.readFile(source, 'utf8')
  await fs.writeFile(target, portableLinks(markdown, source, target))
}

console.log(`Generated ${copies.size} Sley skill references.`)
