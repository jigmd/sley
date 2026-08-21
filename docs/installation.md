---
machine-display: false
---

# Installation

## Python

Caskada requires Python 3.13 or newer.

```bash
pip install caskada
```

## TypeScript And JavaScript

```bash
npm install caskada
```

The package provides ESM and CommonJS exports plus TypeScript declarations.

```typescript
import { Flow, node } from 'caskada'
```

Browser applications can use the ESM bundle from a CDN:

```html
<script type="module">
  import { Flow, node } from 'https://unpkg.com/caskada@3/dist/caskada.js'
</script>
```

## Source Installations

The implementation entry points are
[`python/caskada/__init__.py`](https://github.com/skadaai/caskada/blob/main/python/caskada/__init__.py)
and
[`typescript/caskada.ts`](https://github.com/skadaai/caskada/blob/main/typescript/caskada.ts).
Use the packages for normal applications so Python receives PEP 561 typing and
TypeScript receives declarations, exports, and release metadata.

Continue with [Getting Started](getting_started.md).
