Read CONTRIBUTING.rst for the architecture (parse → intermediate → generators), the layout of ``dev/test_data/`` and the full coding style guide.

Coding Style
============
Prefer functional programming instead of object hierarchy.

If a function is called only once from somewhere and is shorter than 30-40 lines OR has a lot of arguments, inline it. 
We want to keep complexity down!

Always analyze for efficiency -- for example, avoid unnecessary copies of arrays.

Keep the state minimal! Don't introduce state (stateful properties) in classes just because.

Make all global constants ``Final[...]`` in Python. Use readonly containers (``Mapping``, ``Sequence`` etc.).

Workflow
========
While programming, run fast-fail tests first: mypy and black on code generators. 
Once the code is ready, re-record the goldens over the unit tests. 
Summarize the changes with the function signatures, class interfaces and state, and concrete code snippets -- then ask for approval before you run live tests.

* Fast checks: ``python dev/continuous_integration/precommit.py --select reformat ssort mypy ruff``
  (``--overwrite`` reformats and re-sorts in place).
* One test module: ``python -m unittest dev/tests/cpp/test_main.py``
* Re-record golden data: set ``AAS_CORE_CODEGEN_TESTS_RERECORD=1``,
  then review with ``git diff dev/test_data/``.
* The tests cache the pickled symbol tables in ``/tmp/aas-core-codegen-*/``,
  keyed on the meta-model source and the code of ``parse`` and ``intermediate``,
  so parallel worktrees never share stale pickles.
  Old pickles pile up; remove them now and then with
  ``rm -f /tmp/aas-core-codegen-*/model-*.pickle``.
* Live-test fast checks (compile, type-check and lint only; no test runs):
  ``python dev/live_tests/fast_check_<language>.py --select <case> --output_dir <dir>``
  for ``cpp``, ``csharp``, ``golang``, ``java``, ``python`` and ``typescript``.
  Always run them first, and run the live tests only once they pass.
  Pass the same ``--output_dir`` to the live test to re-use the prepared projects.
* Live test: ``python dev/live_tests/live_test_cpp.py --select <case> --output_dir <dir>``
  (C++: clang with ``-DDEBUG`` only, ``VCPKG_ROOT`` must be set).

Golden Test Data
================
These aren't written down anywhere, and Claude tends to break them:
- Never hand-edit files under ``dev/test_data/**/expected*``. Change the generator and re-record.
- Test a new feature with one common meta-model in ``dev/test_data/common_meta_models/``, never one per small case. 
  Each one generates full SDKs for every target. 
  Error cases go to ``dev/test_data/parse/unexpected/`` or ``test_type_inference.py``.
- Generated C++ must stay C++11-compatible, even though the tests compile as C++17.

Style rules that go against normal Python habits
================================================

- Annotate the variables (``lst: List[str] = []``), never with type comments
  (``# type: List[str]``): ruff does not see them and reports the imports as unused.
  This applies to the code generators, not to the generated code.
- Import with a module alias prefix (``cpp_common``, ``golang_naming``). 
  The only allowed symbol aliases are ``I``, ``II``, …
- In ``Stripped`` blocks, use one placeholder per indentation level: ``{IIIII}``, never ``{IIII}{I}``.
- Write multi-line generated code as a ``f"""\`` string, never with ``\n`` escapes:

  .. code-block:: python

      header = f"""\
      {keyword} (
      {I}{indent_but_first_line(condition, I)}
      )"""
- Use icontract ``@require``/``@ensure`` instead of ``assert``. Use a ``Union[...]`` type hint instead of an ``isinstance`` precondition.
- No ``get_`` prefix. 
  Use ``_by_`` for mappings and ``_set`` for sets. No ``_utils``/``_helpers``.
- No ``# TODO``. 
  Notes are ``# NOTE (mristin):`` (where ``mristin`` is your GitHub username). 
  No code in comments. 
  Use ``pathlib``, not ``os.path``. 
  No ``**`` keyword arguments.

Commit Message
==============

We follow Chris Beams' `guidelines on commit messages`_:

1) Separate subject from body with a blank line
2) Limit the subject line to 50 characters
3) Capitalize the subject line
4) Do not end the subject line with a period
5) Use the imperative mood in the subject line, full sentences in the body with a subject ("We ...")
6) Wrap the body at 72 characters
7) Use the body to explain *what* and *why* vs. *how*

.. _guidelines on commit messages: https://chris.beams.io/posts/git-commit/

Keep the commit messages succinct! 1-2 sentences per important point accompanied with a concrete code snippet.

Do not append Co-authored by Claude line in commit messages!

Inline code fragments should be marked with ``...``.

Feature Branches
================
Split work in atomic units in feature branches; prepend ``mristin/`` prefix to the branch name.
