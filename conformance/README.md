# Caskada V3 Conformance

`fixtures/runtime.json` names the portable scenarios and their exact normalized
snapshots. `run-python.py` and `run-typescript.mts` build each scenario through
the corresponding public package. Neither imports private runtime modules.

Run the complete check from the repository root:

```sh
python3 conformance/run-all.py
```

The runner validates the fixture, requires both adapters to implement exactly
the declared ids, compares each adapter with the expected snapshot, and then
compares the two ports directly.
