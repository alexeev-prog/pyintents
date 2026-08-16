import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath("../src"))

project = "pyintents"
author = "alexeev-prog"
version = "0.3.0"
release = "0.3"
project_copyright = f"{datetime.now().year}, Alexeev Bronislav"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.ifconfig",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.githubpages",
]

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "typing": ("https://docs.python.org/3/library/typing.html", None),
}

html_theme = "furo"
html_static_path = ["_static"]
todo_include_todos = True

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "private-members": True,
    "special-members": "__init__",
    "show-inheritance": True,
}

autodoc_inherit_docstrings = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_format = "short"

autosummary_generate = True
autosummary_imported_members = True

add_module_names = True
add_function_parentheses = True

pygments_style = "gruvbox-dark"


def skip(app, what, name, obj, would_skip, options):
    if name == "__init__":
        return False
    return would_skip


def setup(app):
    app.connect("autodoc-skip-member", skip)
