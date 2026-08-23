---
machine-display: false
---

# Installation

## Python

Sley requires Python 3.13 or newer.

```bash
pip install sley
```

## TypeScript And JavaScript

```bash
npm install sley
```

The package provides ESM and CommonJS exports plus TypeScript declarations.

```typescript
import { Flow, node } from 'sley'
```

Browser applications can use the ESM bundle from a CDN:

```html
<script type="module">
  import { Flow, node } from 'https://unpkg.com/sley@0.0.1/dist/sley.js'
</script>
```

## Source Installations

The implementation entry points are
[`python/sley/__init__.py`](https://github.com/jigmd/sley/blob/main/python/sley/__init__.py)
and
[`typescript/sley.ts`](https://github.com/jigmd/sley/blob/main/typescript/sley.ts).
Use the packages for normal applications so Python receives PEP 561 typing and
TypeScript receives declarations, exports, and release metadata.

Continue with [Getting Started](getting_started.md).
