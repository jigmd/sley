import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { DuplicateLinkError, Flow, GraphDefinitionError, GraphElement, Node, node } from '../caskada'

import type { Context } from '../caskada'

interface State {
  count?: number
}

function first(_context: Context<State>): void {}
function second(_context: Context<State>): void {}

describe('v3 graph definitions', () => {
  it('creates distinct configured occurrences with stable names', () => {
    const firstOccurrence = node(first)
    const secondOccurrence = node(first)
    const retrySource = { maxAttempts: 3, delayMs: 25 }
    const configured = node(second, { name: 'configured', retry: retrySource, timeoutMs: 50 })

    retrySource.maxAttempts = 9
    retrySource.delayMs = 99

    assert.ok(firstOccurrence instanceof Node)
    assert.notStrictEqual(firstOccurrence, secondOccurrence)
    assert.equal(firstOccurrence.name, 'first')
    assert.equal(configured.name, 'configured')
    assert.deepEqual({ maxAttempts: configured.retry.maxAttempts, delayMs: configured.retry.delayMs }, { maxAttempts: 3, delayMs: 25 })
    assert.equal(configured.timeoutMs, 50)
    assert.ok(Object.isFrozen(configured.retry))
    assert.equal('handler' in configured, false)
    assert.equal('recovery' in configured, false)
  })

  it('closes direct Node construction and Node or Flow subclassing', () => {
    const DynamicGraphElement = GraphElement as unknown as new (name: string) => GraphElement<State>
    assert.throws(() => new DynamicGraphElement('invalid'), TypeError)
    const DynamicNode = Node as unknown as new (token?: unknown) => Node<State>
    assert.throws(() => new DynamicNode(), TypeError)
    assert.throws(() => new DynamicNode(Symbol('not-the-token')), TypeError)

    class DerivedFlow extends Flow<State> {}
    assert.throws(() => new DerivedFlow(node(first)), TypeError)
  })

  it('uses target-first links and keeps named default distinct from unlabelled', () => {
    const source = node(first)
    const defaultTarget = node(second, { name: 'default-target' })
    const namedTarget = node(second, { name: 'named-target' })

    assert.equal(source.link(defaultTarget), undefined)
    assert.equal(source.link(namedTarget, 'default'), undefined)
    assert.deepEqual(
      source.links().map((link) => [link.action, link.target.name]),
      [
        [null, 'default-target'],
        ['default', 'named-target'],
      ],
    )
    assert.ok(Object.isFrozen(source.links()))
    assert.ok(Object.isFrozen(source.links()[0]))

    const snapshot = source.links()
    assert.throws(() => source.link(node(first)), DuplicateLinkError)
    assert.throws(() => source.link(node(first), 'default'), DuplicateLinkError)
    assert.deepEqual(source.links(), snapshot)
  })

  it('rejects ambiguous dynamic link calls and nonprimitive actions', () => {
    const source = node(first)
    const target = node(second)
    const dynamicLink = source.link.bind(source) as (...arguments_: unknown[]) => void

    for (const arguments_ of [
      [target, undefined],
      [target, null],
      [target, ''],
      [target, new String('named')],
      ['named', target],
      [{}],
      [],
      [target, 'named', 'extra'],
    ]) {
      assert.throws(() => dynamicLink(...arguments_), GraphDefinitionError)
    }
  })

  it('captures Flow configuration and does not retain mutable arrays', () => {
    const entry = node(first)
    const exits = ['approved', 'rejected']
    const flow = new Flow(entry, {
      name: 'review',
      exits,
      concurrency: 4,
      maxActivations: 20,
      combine: () => {},
      recover: () => {},
    })
    exits.push('later')

    assert.equal(flow.name, 'review')
    assert.strictEqual(flow.entry, entry)
    assert.deepEqual(flow.exits, ['approved', 'rejected'])
    assert.ok(Object.isFrozen(flow.exits))
    assert.equal(flow.concurrency, 4)
    assert.equal(flow.maxActivations, 20)
  })

  it('applies Flow defaults and exact option validation', () => {
    const entry = node(first)
    const flow = new Flow(entry)
    assert.equal(flow.name, 'Flow')
    assert.deepEqual(flow.exits, [])
    assert.equal(flow.concurrency, 1)
    assert.equal(flow.maxActivations, undefined)

    const DynamicFlow = Flow as unknown as new (entry: unknown, options?: unknown) => Flow<State>
    const invalidOptions: unknown[] = [
      null,
      [],
      { name: '' },
      { exits: 'done' },
      { exits: ['done', 'done'] },
      { exits: [''] },
      { concurrency: 0 },
      { concurrency: true },
      { maxActivations: 0 },
      { combine: {} },
      { recover: {} },
      { unknown: true },
    ]
    assert.throws(() => new DynamicFlow({}), GraphDefinitionError)
    for (const options of invalidOptions) {
      assert.throws(() => new DynamicFlow(entry, options), GraphDefinitionError)
    }
  })

  it('captures option fields once in declaration order', () => {
    const reads: string[] = []
    const options = Object.create(null) as Record<string, unknown>
    for (const key of ['recover', 'timeoutMs', 'retry', 'name']) {
      Object.defineProperty(options, key, {
        enumerable: true,
        get() {
          reads.push(key)
          if (key === 'name') return 'ordered'
          if (key === 'retry') return { maxAttempts: 2 }
          if (key === 'timeoutMs') return 10
          return () => {}
        },
      })
    }

    const configured = node(first, options)
    assert.equal(configured.name, 'ordered')
    assert.deepEqual(reads, ['name', 'retry', 'timeoutMs', 'recover'])
  })

  it('rejects malformed option records without invoking unknown getters', () => {
    let invoked = false
    const unknown = Object.create(null) as Record<string, unknown>
    Object.defineProperty(unknown, 'unknown', {
      enumerable: true,
      get() {
        invoked = true
        return 1
      },
    })
    assert.throws(() => node(first, unknown), GraphDefinitionError)
    assert.equal(invoked, false)

    const symbolOptions = { [Symbol('field')]: 1 }
    assert.throws(() => node(first, symbolOptions), GraphDefinitionError)

    const hidden = Object.create(null) as Record<string, unknown>
    Object.defineProperty(hidden, 'name', { value: 'hidden', enumerable: false })
    assert.throws(() => node(first, hidden), GraphDefinitionError)

    const cause = new Error('name exploded')
    const throwing = Object.create(null) as Record<string, unknown>
    Object.defineProperty(throwing, 'name', {
      configurable: true,
      enumerable: true,
      get() {
        throw cause
      },
    })
    assert.throws(
      () => node(first, throwing),
      (error: unknown) => error instanceof GraphDefinitionError && error.cause === cause,
    )

    const frameworkCause = new GraphDefinitionError('application error')
    Object.defineProperty(throwing, 'name', {
      configurable: true,
      enumerable: true,
      get() {
        throw frameworkCause
      },
    })
    assert.throws(
      () => node(first, throwing),
      (error: unknown) => error instanceof GraphDefinitionError && error !== frameworkCause && error.cause === frameworkCause,
    )
  })

  it('validates retry numbers and normalizes accepted negative zero', () => {
    const configured = node(first, { retry: { delayMs: -0 } })
    assert.equal(Object.is(configured.retry.delayMs, -0), false)
    assert.equal(configured.retry.delayMs, 0)

    const invalidRetries: unknown[] = [
      null,
      [],
      { maxAttempts: 0 },
      { maxAttempts: true },
      { maxAttempts: Number.MAX_SAFE_INTEGER + 1 },
      { shouldRetry: {} },
      { delayMs: -1 },
      { delayMs: Number.NaN },
    ]
    for (const retry of invalidRetries) {
      assert.throws(() => node(first, { retry: retry as never }), GraphDefinitionError)
    }
  })

  it('uses a stable anonymous fallback', () => {
    const anonymous = node(
      Object.defineProperty((_context: Context<State>) => {}, 'name', {
        value: '',
      }),
    )
    assert.equal(anonymous.name, 'anonymous')
    assert.throws(() => node(first, { name: '' }), GraphDefinitionError)
    assert.throws(() => (node as unknown as (handler: unknown) => Node<State>)({}), GraphDefinitionError)
  })
})
