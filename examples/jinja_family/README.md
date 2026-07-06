# jinja_family

evergen has zero dependencies and does not know about Jinja2. If you want
templates, Jinja2 is *your* dependency: the generator imports it and renders
`templates/*.j2.py` itself. evergen only sees a `gen() -> str`.

Layout:

```text
models.eg.py           controller: loops over ROWS, renders the template per row
templates/model.j2.py  the Jinja2 template
models.py              the signed output (committed)
```

From this directory (`--with jinja2` supplies the generator's dependency):

```sh
uv tool run --from ../.. --with jinja2 evergen --output '{}.py' '{}.eg.py'
```

Expected output:

```text
WROTE models.py <- models.eg.py
```

`models.py` is committed so you can see the result without running anything.
Re-running is idempotent: same repository state, same bytes.
