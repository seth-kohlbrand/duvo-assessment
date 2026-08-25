---
name: tdz-preventer
description: Diagnose and prevent JavaScript temporal-dead-zone failures caused by reading lexical bindings before initialization. Use for "Cannot access before initialization" errors, declaration-order reviews, or React hooks whose callbacks or dependency arrays reference later const/let bindings.
---

# Temporal Dead Zone Review

JavaScript throws a `ReferenceError` when a `let`, `const`, or `class` binding is read before its declaration has executed. Bundling can expose a latent initialization cycle, but ordinary bundlers do not make an otherwise invalid read valid or arbitrarily reorder local declarations.

## Common React pattern

The callback body is evaluated later, but the dependency array is evaluated immediately:

```typescript
// Fails during render because loadAreas is read in the dependency array.
const handleDelete = useCallback(async () => {
  await loadAreas();
}, [loadAreas]);

const loadAreas = useCallback(async () => {
  // ...
}, []);
```

Declare dependencies before consumers:

```typescript
const loadAreas = useCallback(async () => {
  // ...
}, []);

const handleDelete = useCallback(async () => {
  await loadAreas();
}, [loadAreas]);
```

Function declarations are initialized during scope setup and can be appropriate for mutually referenced helpers, but do not change style solely to suppress a symptom without checking the dependency graph.

## Diagnostic workflow

1. Read the first application frame in the production stack trace.
2. Identify the binding named in the error, accounting for source maps and minified names.
3. Search the module for reads that execute during module initialization, render, class definition, default argument evaluation, or dependency-array construction.
4. Trace circular imports; a cycle can expose partially initialized module exports.
5. Move declarations only when it preserves hook ordering and behavior. Otherwise extract shared logic or break the import cycle.
6. Reproduce with the production build and the route or interaction that originally failed.

## Review checklist

- Hooks stay unconditional and in stable order.
- Every dependency-array identifier is initialized before the hook call.
- Module-level constants do not depend on later lexical bindings.
- Circular imports are removed or made initialization-safe.
- Production build and focused runtime test pass with source maps where available.
