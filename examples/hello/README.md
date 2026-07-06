# hello

The smallest possible evergen setup: one generator, one output.

From this directory:

```sh
uvx evergen --output '{}.py' '{}.eg.py'
# or, against this checkout: uv tool run --from ../.. evergen --output '{}.py' '{}.eg.py'
```

Expected output:

```text
WROTE hello.py <- hello.eg.py
```

`hello.py` is committed so you can see the result without running anything.
Re-running the command is idempotent: the body bytes are identical, so git
stays clean.
