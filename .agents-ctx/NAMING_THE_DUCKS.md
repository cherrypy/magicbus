# Naming the Ducks

Canonical names for this project, and how to refer to it in
prose. Other files in `.agents-ctx/` (and any generated content)
should say "the project" rather than hardcoding one of these --
reach for a specific name only when the distinction actually
matters (e.g. citing a package, an import, or a repository URL).

## Distribution / PyPI name: `MagicBus`

The installable, published name -- passed as `name` to
`setuptools.setup()` in `setup.py`. This is also the preferred way
to refer to the project by name in prose. Packaging tools
normalize it to `magicbus` -- that's the same distribution.

## Python import name: `magicbus`

`import magicbus` is what code actually imports. The test suite
ships inside it, as `magicbus.test`.

## GitHub repository slug: `cherrypy/magicbus`

Use it verbatim when it's actually the repository being
referenced (URLs, `gh` invocations, PR/issue citations) -- not as
a stand-in for the project's name in prose.

## Don't confuse it with CherryPy

MagicBus is maintained by the CherryPy team, but it's a separate
project from CherryPy, released from its own repository. Say which
one is meant.
