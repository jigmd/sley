from __future__ import annotations

import unittest

from caskada import Failure


class ScaleStructureTests(unittest.TestCase):
    def test_large_failure_replacement_chain_keeps_identity_and_bounded_repr(
        self,
    ) -> None:
        previous: Failure | None = None
        for failure_id in range(1, 10_001):
            previous = Failure(
                failure_id=failure_id,
                kind="handler",
                message="Node handler raised",
                cause=None,
                scope_id=1,
                activation_id=2,
                element_id=1,
                attempt=1,
                detail=None,
                previous=previous,
            )

        assert previous is not None
        rendered = repr(previous)
        self.assertIn("failure_id=10000", rendered)
        self.assertIn("previous_failure_id=9999", rendered)
        self.assertLess(len(rendered), 300)
        peer = Failure(
            failure_id=previous.failure_id,
            kind=previous.kind,
            message=previous.message,
            cause=previous.cause,
            scope_id=previous.scope_id,
            activation_id=previous.activation_id,
            element_id=previous.element_id,
            attempt=previous.attempt,
            detail=previous.detail,
            previous=previous.previous,
        )
        self.assertIsNot(previous, peer)
        self.assertNotEqual(previous, peer)


if __name__ == "__main__":
    unittest.main()
