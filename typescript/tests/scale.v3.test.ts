import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import type { Failure } from '../caskada'

describe('v3 scale structures', () => {
  it('keeps a 10,000-replacement chain reference-based', () => {
    let previous: Failure | null = null
    for (let failureId = 1; failureId <= 10_000; failureId += 1) {
      previous = {
        failureId,
        kind: 'handler',
        message: 'Node handler raised',
        cause: null,
        scopeId: 1,
        activationId: 2,
        elementId: 1,
        attempt: 1,
        detail: null,
        previous,
      }
    }

    assert.notEqual(previous, null)
    assert.equal(previous!.failureId, 10_000)
    assert.equal(previous!.previous!.failureId, 9_999)
    const peer: Failure = { ...previous! }
    assert.notEqual(previous, peer)
  })
})
