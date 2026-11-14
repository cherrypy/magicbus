# Where to Look First

When picking up a task, get oriented before proposing anything.
Read, in this order:

1. The packaging metadata -- what the project is, what it depends
   on, what it exposes.
2. The source of the module the task is about.
3. The shared test fixtures, then the tests for that module --
   they are the behavioral contract.
4. `tox.ini` and `.pre-commit-config.yaml` -- how things get run
   locally and in CI.
5. The main CI/CD workflow.

Here:

1. `setup.py` (the metadata) and `pyproject.toml` (the build
   backend and `setuptools-scm`).
2. `magicbus/<module>.py`, or `magicbus/plugins/<plugin>.py` for
   the bundled plugins.
3. `magicbus/test/__init__.py` -- the shared helpers, such as the
   test web server and process wrappers -- then
   `magicbus/test/test_<topic>.py`.
4. As above, plus `toxfile.py` -- an in-tree tox plugin making
   `build-dists` reproducible and reporting runtime details in CI.
5. `.github/workflows/ci-cd.yml`, which delegates to
   `tox-dev/workflow`'s `reusable-tox.yml`.

Other places worth knowing:

- `dependencies/lock-files/` -- the constraints the dist builds
  are pinned to.
- `docs/` -- Sphinx docs (RST); change notes go under
  `docs/changelog-fragments.d/`, and `CHANGES.rst` is generated
  from them.
