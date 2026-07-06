from pathlib import Path

from jinja2 import Template

HERE = Path(__file__).parent

ROWS = [
    {"name": "User", "table": "users"},
    {"name": "Invoice", "table": "invoices"},
]


def render(template_name, **data):
    text = (HERE / "templates" / template_name).read_text()
    return Template(text).render(**data)


def gen():
    return "\n\n".join(render("model.j2.py", **row) for row in ROWS) + "\n"
