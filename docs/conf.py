#! /usr/bin/env python3
# Requires Python 3.6+
# pylint: disable=invalid-name
"""Configuration of Sphinx documentation generator."""

extensions = ['sphinx.ext.autodoc', 'jaraco.packaging.sphinx', 'rst.linker']

master_doc = "index"

link_files = {
    '../CHANGES.rst': dict(
        using=dict(GH='https://github.com'),
        replace=[
            dict(
                pattern=r'(Issue #|\B#)(?P<issue>\d+)',
                url='{package_url}/issues/{issue}',
            ),
            dict(
                pattern=r'(?m:^((?P<scm_version>v?\d+(\.\d+){1,2}))\n[-=]+\n)',
                with_scm='{text}\n{rev[timestamp]:%d %b %Y}\n',
            ),
            dict(
                pattern=r'PEP[- ](?P<pep_number>\d+)',
                url='https://www.python.org/dev/peps/pep-{pep_number:0>4}/',
            ),
        ],
    )
}


# intersphinx
extensions += ['sphinx.ext.intersphinx']
intersphinx_mapping = {
    'cheroot': ('https://cheroot.cherrypy.org/en/latest/', None),
    'cherrypy': ('https://docs.cherrypy.org/en/latest/', None),
    'python': ('https://docs.python.org/3', None),
    'python2': ('https://docs.python.org/2', None),
}
