import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { CompiledFlow, Flow, GraphDefinitionError, GraphElement, node } from '../caskada'

import type { Context } from '../caskada'

interface State {
  value?: string
}

function handler(_context: Context<State>): void {}

class ForeignElement extends GraphElement<State> {
  protected readonly _caskadaKind = 'node' as const

  constructor() {
    super('foreign')
  }
}

describe('v3 compilation', () => {
  it('uses normative breadth-first IDs for nested scopes', () => {
    const parentEntry = node(handler, { name: 'parent_entry' })
    const childFirst = node(handler, { name: 'child_first' })
    const childSecond = node(handler, { name: 'child_second' })
    const after = node(handler, { name: 'after' })
    const child = new Flow(childFirst, { name: 'child', concurrency: 2 })
    parentEntry.link(child)
    child.link(after)
    childFirst.link(childSecond)

    const description = new Flow(parentEntry, { name: 'root' }).compile().describe()
    assert.deepEqual(
      description.elements.map((element) => [element.element_id, element.name]),
      [
        [1, 'root'],
        [2, 'parent_entry'],
        [3, 'child'],
        [4, 'after'],
        [5, 'child_first'],
        [6, 'child_second'],
      ],
    )
    assert.deepEqual(
      description.scope_definitions.map((scope) => [scope.scope_definition_id, scope.entry_element_id]),
      [
        [1, 2],
        [2, 5],
      ],
    )
    assert.equal(description.auto_max_concurrency, 2)
  })

  it('creates one placement per definition identity and scope', () => {
    const start = node(handler, { name: 'start' })
    const shared = node(handler, { name: 'shared' })
    const child = new Flow(shared, { name: 'child', concurrency: 2 })
    const sibling = new Flow(shared, { name: 'sibling', concurrency: 3 })
    start.link(child, 'first')
    start.link(child, 'second')
    start.link(sibling, 'third')

    const description = new Flow(start, { name: 'root' }).compile().describe()
    assert.deepEqual(
      description.elements.filter((element) => element.name === 'shared').map((element) => element.parent_scope_definition_id),
      [2, 3],
    )
    assert.deepEqual(
      description.elements[1]!.links.map((link) => link.target_element_id),
      [3, 3, 4],
    )
    assert.equal(description.auto_max_concurrency, 3)
  })

  it('accepts graph cycles and rejects recursive Flow containment', () => {
    const first = node(handler, { name: 'first' })
    const second = node(handler, { name: 'second' })
    first.link(second)
    second.link(first)
    const cycle = new Flow(first).compile().describe()
    assert.equal(cycle.elements.length, 3)
    assert.equal(cycle.elements[2]!.links[0]!.target_element_id, 2)

    const recursiveEntry = node(handler, { name: 'recursive-entry' })
    const recursive = new Flow(recursiveEntry, { name: 'recursive' })
    recursiveEntry.link(recursive)
    assert.throws(() => recursive.compile(), GraphDefinitionError)
  })

  it('rejects unknown graph element implementations', () => {
    const entry = node(handler)
    entry.link(new ForeignElement())
    assert.throws(() => new Flow(entry).compile(), GraphDefinitionError)
  })

  it('makes CompiledFlow factory-only and non-subclassable at runtime', () => {
    const DynamicCompiledFlow = CompiledFlow as unknown as new (token?: unknown) => CompiledFlow<State>
    assert.throws(() => new DynamicCompiledFlow(), TypeError)
    assert.throws(() => new DynamicCompiledFlow(Symbol('not-the-token')), TypeError)

    class DerivedCompiledFlow extends CompiledFlow<State> {}
    const DynamicDerived = DerivedCompiledFlow as unknown as new (token?: unknown) => DerivedCompiledFlow
    assert.throws(() => new DynamicDerived(), TypeError)
  })

  it('isolates a compiled topology from later definition changes', () => {
    const entry = node(handler, { name: 'entry' })
    const firstTarget = node(handler, { name: 'first-target' })
    const laterTarget = node(handler, { name: 'later-target' })
    entry.link(firstTarget)
    const root = new Flow(entry, { name: 'root' })
    root.link(node(handler, { name: 'ignored-root-target' }))

    const compiled = root.compile()
    const before = compiled.describe()
    entry.link(laterTarget, 'later')
    const after = root.compile().describe()

    assert.deepEqual(compiled.describe(), before)
    assert.deepEqual(before.elements[0]!.links, [])
    assert.equal(
      before.elements.some((element) => element.name === 'ignored-root-target'),
      false,
    )
    assert.equal(before.elements.length, 3)
    assert.equal(after.elements.length, 4)
    assert.ok(Object.isFrozen(before))
    assert.ok(Object.isFrozen(before.elements))
    assert.ok(Object.isFrozen(before.scope_definitions[0]!.exits))
    assert.throws(() => (before.elements as unknown[]).pop(), TypeError)
  })
})
