************
Contributing
************

Coordinate First
================

Before you create a pull request, please `create a new issue`_ first to coordinate.

It might be that we are already working on the same or similar feature, but we 
haven't made our work visible yet.

.. _create a new issue: https://github.com/aas-core-works/aas-core-codegen/issues/new

Create a Development Environment
================================

We usually develop in a `virtual environment`_.
To create one, change to the root directory of the repository and invoke:

.. code-block::

    python -m venv venv


You need to activate it. On *nix (Linux, Mac, *etc.*):

.. code-block::

    source venv/bin/activate

and on Windows:

.. code-block::

    venv\Scripts\activate

.. _virtual environment: https://docs.python.org/3/tutorial/venv.html

Install Development Dependencies
================================

Once you activated the virtual environment, you can install the package using ``pip``:

.. code-block::

    pip3 install --editable .

The `--editable <pip-editable_>`_ option is necessary so that all the changes
made to the repository are automatically reflected in the virtual environment 
(see also `this StackOverflow question <pip-editable-stackoverflow_>`_).

.. _pip-editable: https://pip.pypa.io/en/stable/reference/pip_install/#install-editable
.. _pip-editable-stackoverflow: https://stackoverflow.com/questions/35064426/when-would-the-e-editable-option-be-useful-with-pip-install

You also have to install the development dependencies, including different development modules:

.. code-block::

    pip3 install --editable dev

Background Literature
=====================
Please make yourself familiar with a general literature on compiler design.
For example, `Crafting Interpreters`_ is a good book.

.. _Crafting Interpreters: https://craftinginterpreters.com/

Please also read relevant publications related to the aas-core-codegen:

* https://www.researchgate.net/publication/375497058_Empowering_Industry_40_with_Generative_and_Model-Driven_SDK_Development
* https://www.researchgate.net/publication/356039469_Generative_and_Model-driven_SDK_development_for_the_Industrie_40_Digital_Twin,
* https://www.researchgate.net/publication/373325991_Generation_of_Digital_Twins_for_Information_Exchange_Between_Partners_in_the_Industrie_40_Value_Chain,

Structure Overview
==================
Directory Structure
-------------------
The repository is organized as follows:

.. code-block::

    aas-core-codegen/
    ├── aas_core_codegen/       Main Python package
    │   ├── common.py           Shared data structures and functions
                                (Error, Identifier, *etc.*)
    │   ├── main.py             Entry point (aas-core-codegen console command)
    │   ├── run.py              Run logic shared across generators
                                (coupled to main.py, but also used in tests)
    │   ├── naming.py           Generation of target-specific names based on identifiers
    │   ├── specific_implementations.py  Look-up of implementation-specific snippets
    │   ├── stringify.py        Debug stringification of internal structures
    │   ├── parse/              Parsing meta-model source files into an AST
    │   ├── intermediate/       Intermediate Representation (IR)
    │   ├── infer_for_schema/   Schema-constraint inference from the IR
    │   ├── yielding/           Linearized yielding for languages without yield
    │   ├── smoke/              Verify a model by running a smoke-test transpilation
    │   ├── cpp/                C++ SDK generator
    │   ├── csharp/             C# SDK generator
    │   ├── golang/             Go SDK generator
    │   ├── java/               Java SDK generator
    │   ├── jsonschema/         JSON Schema generator
    │   ├── python/             Python SDK generator
    │   ├── typescript/         TypeScript SDK generator
    │   └── xsd/                XSD schema generator
    ├── dev/                    Development tooling (separate installable package)
    │   ├── continuous_integration/  Pre-commit and CI scripts
    │   ├── dev_scripts/        Developer helper scripts
    │   ├── live_tests/         Live end-to-end tests against temporary-generated SDKs
    │   ├── tests/              Unit and integration tests
    │   └── test_data/          Golden test data (recorded expected output)
    ├── pyproject.toml          Package configuration and entry-point declaration
    ├── CONTRIBUTING.rst        This file
    ├── README.rst              Project overview and usage instructions
    └── CHANGELOG.rst           Release notes

The main package lives under `aas_core_codegen/`_.
The development tooling -- scripts, tests (both integration and unit), pre-commit checks, *etc.* -- lives under `dev/`_.
For example, the script to convert an existing file into a sequence of stripped text blocks lives at
`dev/dev_scripts/convert_file_into_sequence_of_stripped_blocks.py`_.

.. _aas_core_codegen/: https://github.com/aas-core-works/aas-core-codegen/tree/main/aas_core_codegen
.. _dev/: https://github.com/aas-core-works/aas-core-codegen/tree/main/dev
.. _dev/dev_scripts/convert_file_into_sequence_of_stripped_blocks.py: https://github.com/aas-core-works/aas-core-codegen/blob/main/dev/dev_scripts/convert_file_into_sequence_of_stripped_blocks.py

Module Structure
----------------
The main entry point is ``aas_core_codegen/main.py``, which corresponds to the ``aas-core-codegen`` console command declared in ``pyproject.toml``.
It delegates the bulk of the work to ``run.py``, which contains the run logic shared across generators and is also used directly in tests.

The transpilation pipeline follows three major stages, as described in the `background literature <Background Literature_>`_: parsing the formalized meta-modelinto an AST, interpreting the AST into an Intermediate Representation (IR), and finally generating code from the IR for each target language.

``parse/`` -- Parse the Meta-model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The ``parse`` module takes the source of the formalized AAS meta-model -- written in a strongly-reduced subset of Python -- and translates it into a parsed AST.
The Python source is first tokenised with the ``asttokens`` library (``_translate.source_to_atok``), then walked and translated into our own typed structures (``_translate.atok_to_symbol_table``).

The result is a ``SymbolTable`` holding all the classes, enumerations, constants and constrained primitives found in the meta-model source.
Each of these objects is an instance of one of the types defined in ``_types.py`` (``AbstractClass``, ``ConcreteClass``, ``Enumeration``, *etc.*).
At this stage all cross-references -- superclasses, property types, method argument types -- are still plain ``Identifier`` strings; they are resolved only in the ``intermediate`` stage.

``parse/tree.py`` provides our custom AST for constraint expressions.
It is a deliberate simplification of the full Python AST: only the constructs that appear in meta-model constraints are represented.
Nodes carry a reference back to the original ``ast.AST`` node for error reporting.
The module exposes ``Visitor`` and ``Transformer`` base classes for working with the tree.

``parse/retree/`` provides parsing and manipulation of the regular expressions that appear in meta-model constraints.
Because target languages have incompatible regex flavours -- in particular, C# cannot express character points above the UTF-16 range as a single literal -- we parse regexes into our own AST (``retree._types``) and re-render them per target platform *via* ``retree._render``.
The ``retree._fix`` module applies the platform-specific fixes; the ``retree._parse`` module contains the parser; and ``retree._visitor`` provides a visitor base class for the regex AST.

``intermediate/`` -- Intermediate Representation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The ``intermediate`` module interprets the parsed ``SymbolTable`` into a semantically
richer Intermediate Representation.
Whereas the ``parse`` module focuses purely on syntax, ``intermediate`` resolves cross-references, infers types, and crystallises the semantics needed by the code generators.

The translation is a **two-pass process** (implemented in ``_translate.py``):

* **First pass** -- all ``OurType`` symbols (classes, enumerations, constrained primitives) are instantiated as placeholder objects and collected into a symbol table.
* **Second pass** -- each placeholder is populated: string-based references in properties, method signatures, inheritance lists, and constraint expressions are resolved to the actual symbol objects created in the first pass.

The types of the IR live in ``_types.py``.
They are mutated during the two-pass translation but are thereafter treated as immutable (see ``Final`` and Constant Containers in the `Coding Style Guide`_).

The remaining submodules each handle one aspect of the interpretation:

* ``type_inference.py`` -- infers a type for every node in a ``parse.tree`` constraint expression.
  The types roughly follow the annotations in ``_types.py`` but are not identical; for example, a ``LENGTH`` pseudo-primitive exists only during type inference.
* ``construction.py`` -- analyses constructor bodies to understand how each class initialises its properties.
* ``pattern_verification.py`` -- analyses pattern-verification functions (functions defined in a meta-model that check a string against a regular expression), and records them in the IR so generators can emit the corresponding checks.
* ``revm.py`` -- transpiles regular expressions to instructions for a non-backtracking virtual machine (based on Ken Thompson's approach).
  The regular expression engines in many standard libraries (such as Java or C++) have exponential worst-case complexity on certain inputs; the VM provides linear-time matching and is used wherever the target language does not ship a comparable engine.
* ``doc.py`` -- types for resolved references inside docstrings.
  Documentation is parsed from RST-formatted docstrings and the symbol references within it are resolved to IR symbols.
* ``_hierarchy.py`` -- builds an ontology of the class hierarchy (ancestors, descendants, topological order) that generators query when emitting visitor dispatching or inheritance-related code.

``infer_for_schema/`` -- Schema Constraint Inference
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Schemas such as JSON Schema and XSD can express only a subset of the constraints found in the IR (lengths, patterns, enumeration membership).
The ``infer_for_schema`` module walks the constraint ASTs and matches structural patterns to extract the constraints that a schema can represent.
The result is a set of ``LenConstraint``, ``PatternConstraint``, *etc.* objects that the schema generators consume directly.
The matching logic lives in ``infer_for_schema/match.py``.

``yielding/`` -- Linearized Yielding
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Some target languages (most notably C++) lack a native ``yield`` / generator construct.
For those languages, code that would naturally be written as a generator must instead be linearized into an explicit state machine.
The ``yielding`` module transforms a control-flow graph that uses ``yield`` into a sequence of coroutine-compatible steps that can be rendered as a ``while``/``switch`` loop in the target language.

Language SDK Generators
-----------------------
Each supported language has its own generator package under ``aas_core_codegen/<language>/``.
The packages share a consistent internal layout described below.

``main.py``
^^^^^^^^^^^
The entry point for an SDK generator.
It receives the ``SymbolTable`` from ``intermediate`` and orchestrates calls to the submodules in ``lib/`` to produce the full SDK output on disk.

Shared Modules
^^^^^^^^^^^^^^
Each generator contains a set of modules shared across its ``lib/`` submodules:

* ``common.py`` -- helper functions and constants used by multiple submodules within the same generator.
  Examples include formatting utilities, primitive-type mappings, or reusable code fragments.
* ``naming.py`` -- derives language-idiomatic names (classes, interfaces, properties, methods, *etc.*) from the ``Identifier`` strings in the IR.
  For example, how to derive an interface name in Go or a property name in TypeScript from the IR identifier.
* ``description.py`` -- renders the documentation from the IR into the language-specific comment syntax (Sphinx docstrings for Python, XML doc-comments for C#, JSDoc for TypeScript, *etc.*).
* ``transpilation.py`` -- translates ``parse.tree`` constraint expressions from the IR into executable code in the target language.
  This covers the bodies of invariant checks and verification functions.

``lib/``
^^^^^^^^
Each submodule in ``lib/`` is responsible for generating one component of the output SDK.
The naming ``_generate_<component>.py`` mirrors the component it produces.
Most languages share the following components in the generated SDK:

* ``types`` -- data structures representing the meta-model classes and enumerations.
* ``constants`` -- global constant values defined in the meta-model (*e.g.*, constant sets of strings).
* ``stringification`` -- functions to convert enumerations to and from their string representations.
* ``jsonization`` -- de/serialization of model instances to and from JSON.
* ``xmlization`` -- de/serialization of model instances to and from XML.
* ``verification`` -- functions that check the invariants defined in the meta-model.
* ``common`` -- helpers shared across the generated SDK components.
* ``xmlcommon`` -- the XML primitives which every reader and writer of XML shares: the whitespace of XSD, the checks of the namespace, the consumption of the tags and the path into the document.
  It exists so that the de/serialization of the model and the ``xmlrpc`` below do not each carry a copy of them.

Additional components appear where the language or its community conventions require them:

* ``reporting`` (C#, Go, Java, Python) -- data structures and utilities for collecting and formatting de/serialization and verification errors, used in languages where exception-based error propagation is not the preferred idiom.
  In Python it is narrower: it carries only the error paths of the verification, as the de/serialization there reports through exceptions instead.
* ``enhancing`` (C#, C++, Go, Java) -- wrapping and unwrapping model instances with custom user-defined data without modifying the generated types; see the `documentation on enhancing in Go`_.
* ``visitation`` (C#, C++, Java) -- ``Visitor`` and ``Transformer`` base classes for traversing the model hierarchy; see `Visitor pattern`_.
* ``copying`` (C#, Java) -- functions to produce deep copies of model instances.
* ``generation`` (Java) -- builder classes for constructing model instances incrementally.
* ``xmlrpc`` (C#, C++, Go, Java, Python, TypeScript) -- the subset of XML-RPC -- ``<boolean>``, ``<double>``, ``<string>``, ``<array>`` and ``<struct>`` -- which carries a JSON-able value, since JSON prescribes no XML representation of its own.
  Generated only for a meta-model which actually uses a JSON-able type.
* ``jsonvalueverification`` (C#, C++, Python) -- the walk which checks that a value is JSON-able at any depth, split out of ``verification`` where the language rewards a module which depends on no class of the meta-model.
  Generated only for a meta-model which actually uses a JSON-able type.
* ``index`` (TypeScript) -- a barrel ``index.ts`` file that re-exports all public symbols from the other SDK modules.
* ``iteration`` (C++) -- free functions to descend into and iterate over model instances, serving the same role that ``visitation`` fills for class-based languages.
* ``revm`` (C++) -- regular expressions, emitted because C++ lacks a cross-platform, linear-time regex engine in its standard library.
* ``wstringification`` (C++) -- wide-string (``std::wstring``) variants of the stringification functions.

.. _documentation on enhancing in Go: https://github.com/aas-core-works/aas-core3.1-golang#enhancing
.. _Visitor pattern: https://en.wikipedia.org/wiki/Visitor_pattern

``tests/``
^^^^^^^^^^
Each submodule in ``tests/`` generates source files for the SDK's own test suite.
The generated tests cover serialization round-trips, verification of valid and invalid instances, visitor traversal, and other SDK-level contracts.
The submodules follow the same naming convention as ``lib/``: one ``_generate_<component>`` module per test suite produced.

Language-specific Modules
^^^^^^^^^^^^^^^^^^^^^^^^^^
Some languages require additional inference before code can be emitted.
These inferences live in dedicated modules at the top level of the generator package:

* ``golang/pointering.py`` -- determines which IR nodes correspond to Go pointer (``*T``) types versus value types.
  Go distinguishes them at the syntax level, so the generator must resolve nullability before rendering any expression.
* ``cpp/optionaling.py`` -- analogous to ``pointering.py`` for C++: determines which nodes carry ``std::optional<T>`` types.
* ``cpp/yielding.py`` -- emits the linearized coroutine steps produced by ``aas_core_codegen.yielding`` into C++ syntax (``while``/``switch`` state machines).
* ``java/optional.py`` -- determines which nodes use ``Optional<T>`` versus bare types in Java.

Live Tests
----------
The live tests are end-to-end integration scripts that verify the generated SDKs are not only textually correct but also actually compile, type-check, and pass their own unit tests.
They live in `dev/live_tests/`_ and are run manually -- they are not part of the pre-commit pipeline because they require language-specific toolchains that are not universally available.

.. _dev/live_tests/: https://github.com/aas-core-works/aas-core-codegen/tree/main/dev/live_tests

One script exists per supported language:

* ``dev/live_tests/live_test_cpp.py`` -- C++
* ``dev/live_tests/live_test_csharp.py`` -- C#
* ``dev/live_tests/live_test_golang.py`` -- Go
* ``dev/live_tests/live_test_java.py`` -- Java
* ``dev/live_tests/live_test_python.py`` -- Python
* ``dev/live_tests/live_test_typescript.py`` -- TypeScript

How a Live Test Works
^^^^^^^^^^^^^^^^^^^^^
Each script iterates over the golden test cases recorded in ``dev/test_data/main/<language>/expected/``.
For every case it:

1. Copies the expected output files (the generated SDK source) into a temporary working directory (or into ``--output_dir`` if given).
2. Synthesizes the project boilerplate that is not part of the generated SDK itself -- build files, dependency manifests, project configuration -- because the code generator only produces the library source, not a complete project.
3. Compiles (or type-checks) the assembled project.
4. If a matching sub-directory exists under ``dev/test_data/live_tests/<language>/test_data/<case>/``, copies that test data into the project and runs the generated SDK's own unit test suite.
   The tests are first executed in *record mode* (the ``*_TEST_RECORD_MODE`` environment variable is set to ``1``) so that any missing golden traces are written out.

Command-line Options
^^^^^^^^^^^^^^^^^^^^
All live-test scripts accept the same two options:

``--output_dir PATH``
    Write the assembled project into ``PATH`` instead of a temporary directory.
    The directory is **not** deleted after the run, which is useful for inspecting failures or iterating on a fix.
    If omitted, a temporary directory is created and removed automatically.

``--select REGEX``
    Run only the test cases whose directory name matches the given regular expression.
    For example, ``--select primitive_types`` runs only the ``primitive_types`` case.

Prerequisites
^^^^^^^^^^^^^
Each script requires the corresponding language toolchain to be installed and available on ``PATH``:

*C++*
    ``cmake`` and a C++ compiler.
    Dependencies (``nlohmann-json``, ``expat``, ``tl-optional``, ``tl-expected``) are managed via `vcpkg`_.
    The ``VCPKG_ROOT`` environment variable must point to the root of a vcpkg installation.

    .. _vcpkg: https://github.com/microsoft/vcpkg

*C#*
    The .NET SDK (``dotnet`` command).
    The script targets ``net6.0``.

*Go*
    The ``go`` toolchain and ``goimports``.
    Install ``goimports`` with:

    .. code-block::

        go install golang.org/x/tools/cmd/goimports@latest

    The script looks for ``goimports`` on ``PATH`` and falls back to ``~/go/bin/goimports``.

*Java*
    ``mvn`` (Maven) and a JDK compatible with Java 17.
    The script synthesizes a ``pom.xml`` and runs ``mvn test-compile`` and ``mvn test``.

*Python*
    Python 3.9 or later (the same interpreter that runs the script).
    The script creates a dedicated virtual environment inside the temporary project directory and installs ``mypy`` and ``pylint`` to type-check and lint the generated code before running the tests.

*TypeScript*
    ``node`` and ``npm``.
    The script installs all dependencies *via* ``npm install`` and then runs lint, build, and jest tests.

Development Scripts
-------------------
The development scripts in `dev/dev_scripts/`_ assist with the development tasks such as authoring code-generation templates and debugging regex handling.

.. _dev/dev_scripts/: https://github.com/aas-core-works/aas-core-codegen/tree/main/dev/dev_scripts

``convert_file_into_sequence_of_stripped_blocks.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The code generators build their output from ``Stripped(...)`` string blocks in which indentation is expressed as ``{I}``, ``{II}``, ``{III}``, *etc.* placeholders (one ``I`` per indentation level) rather than literal spaces or tabs.
Writing these blocks by hand is tedious and error-prone.
This script automates the conversion: given a plain source file it splits the content into top-level blocks (separated by blank lines that are not inside an indented region), escapes backslashes and curly brackets, and replaces leading indentation with the corresponding placeholder.
The result is printed to stdout as a series of ``Stripped(...)`` expressions ready to be pasted into a generator module.

``replace-curly-brackets-backslashes-and-*-indent.html``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Three browser-based (no server required) equivalents of ``convert_file_into_sequence_of_stripped_blocks.py``, one per indentation style:

* ``replace-curly-brackets-backslashes-and-four-space-indent.html``
* ``replace-curly-brackets-backslashes-and-two-space-indent.html``
* ``replace-curly-brackets-backslashes-and-tab-indent.html``

Open the appropriate file in a browser, paste a code snippet into the upper text area, and the lower text area immediately shows the escaped and placeholder-substituted result.
Checkboxes allow suppressing backslash or curly-bracket escaping when they are not needed.
A *Copy* button copies the output to the clipboard.
These pages are most convenient for converting small ad-hoc snippets interactively, whereas the Python script is better suited for processing entire files.

``compare_rendered_regexes_against_source_py.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The ``parse/retree/`` module re-renders regular expressions into platform-specific forms.
For each test case under ``dev/test_data/parse_retree/expected/`` the test data contains a ``source.py`` file (the original Python-literal regex) and a ``rendered_regex.txt`` file (the expected re-rendered form).
This script walks all those pairs and prints the cases where the ``repr`` of ``rendered_regex.txt`` no longer matches ``source.py``, making it easy to spot regressions or inconsistencies after changes to the regex renderer.

``draw_bipartite_graph_based_on_lines.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
When large blocks of generated code are reordered rather than changed, ``diff`` output becomes noisy and hard to read.
This script helps by treating each line as a node and printing, for every line in ``--ours`` that also appears in ``--theirs``, the pair of line numbers.
The resulting bipartite mapping shows which blocks have simply moved, making it easier to identify a minimal reordering and to verify that no content was accidentally lost.

Test Data
---------
Almost all tests in ``dev/tests/`` are *golden tests*: the test runs the production code, serialises the result to text, and compares it against a pre-recorded expected file.
If the ``AAS_CORE_CODEGEN_TESTS_RERECORD`` environment variable is set, the test writes it (record mode); on subsequent runs without this environment variable the test fails if the output differs from the recorded file.
This makes it easy to review changes: ``git diff dev/test_data/`` shows exactly what the output of the generators changed.

The golden files live in ``dev/test_data/``.
The sub-directory structure mirrors the test-module structure: a test in ``dev/tests/cpp`` looks for its golden data under ``dev/test_data/cpp/``.

Each top-level sub-directory of ``dev/test_data/`` serves a distinct purpose:

``common_meta_models/``
    Meta-model source files that are reused by multiple test suites.
    For example, ``common_meta_models/aas_core_meta.v3.py`` is the full AAS V3.0 meta-model and is referenced by the intermediate and end-to-end main tests.

``parse/``
    Golden data for ``dev/tests/parse/``, which tests the ``aas_core_codegen.parse`` module.
    Cases are split into ``expected/`` (valid meta-models that must parse successfully) and ``unexpected/`` (meta-models that must fail with a specific error).
    Each leaf directory contains a ``meta_model.py`` (the input) and either an ``expected_symbol_table.txt`` (the serialised parse result) or an ``expected_error.txt`` (the expected error message).

``parse_retree/``
    Golden data for ``dev/tests/parse_retree/``, which tests the ``aas_core_codegen.parse.retree`` regex parser and renderer.
    Each leaf directory under ``expected/`` contains ``source.py`` (the input regex string literal), ``expected_parsed_regex.txt`` (the serialised regex AST), and ``rendered_regex.txt`` (the re-rendered platform-neutral form).
    Leaf directories under ``unexpected/`` contain ``source.py`` and ``expected_error.txt``.

``intermediate/``
    Golden data for ``dev/tests/intermediate/``, which tests the ``aas_core_codegen.intermediate`` module.
    The layout mirrors ``parse/``: ``expected/`` cases contain ``meta_model.py`` and ``expected_symbol_table.txt``; ``unexpected/`` cases contain ``meta_model.py`` and ``expected_error.txt``.

``intermediate_revm/``
    Golden data for the REVM (regular-expression virtual machine) tests in ``dev/tests/intermediate/``.
    Each case has ``expected/`` and ``unexpected/`` sub-trees, following the same convention as ``intermediate/``.

``smoke/``
    Golden data for ``dev/tests/smoke/``, which runs a smoke transpilation over every meta-model under ``smoke/test_main/expected/`` and verifies that the transpilation either succeeds or fails with a known error.
    ``unexpected/`` cases each contain a ``meta_model.py`` and an ``expected_stderr.txt``.

``main/``
    The most important test data directory: end-to-end golden tests that run the full transpilation pipeline for every target language.
    The structure is ``main/<language>/expected/<case>/``.
    Each case directory contains:

    * ``meta_model.py`` -- the input meta-model.
    * ``input/snippets/`` -- implementation-specific snippets supplied to the generator.
    * ``expected_output/`` -- the expected SDK source tree produced by the generator, stored file-by-file.

    These expected outputs serve a dual purpose: they are compared against during the test run *and* they are copied into the temporary project by the live tests (see `Live Tests`_).

``csharp/``
    Unit-test golden data for individual C# generator modules, *e.g.*,
    ``csharp/test_types/`` for ``_generate_types.py`` and ``csharp/test_verification/`` for ``_generate_verification.py``.
    Each leaf directory contains ``meta_model.py`` and an expected ``.cs`` snippet file that covers only the module under test, not a full SDK output.

``live_tests/``
    Test data used by the generated SDK's own unit tests when running under a live test.
    The structure is ``live_tests/<language>/test_data/<case>/``.
    Each case directory contains serialised AAS instances (organised as ``Json/`` and ``Xml/`` sub-directories) that the generated test suite reads to verify de/serialisation round-trips and constraint checking.
    See `Live Tests`_ for how this data is consumed.

Coding Style Guide
==================
Typing
------
Always write explicit types in function arguments.
If you really expect any type, mark that explicitly with ``Any``.
Also always mark your local variables with a type if it can not be deduced.

For example:

.. code-block:: python

    lst = []  # type: List[str]

For files, use ``typing.IO``.

We prefer to put types in comments if they are short for readability.
However, put them in code when they are multi-line:

.. code-block:: python

    some_map: Optional[
        Dict[
          SomeType,
          AnotherType
        ]
    ] = None

Variable Names
--------------
Put ``_set`` for sets.

Prefer to designate the key with ``_by_`` suffix.
For example, ``our_types_by_name`` is a mapping string (a name) 🠒 ``OurType``.

Method Names
------------
Do not put ``get_`` in method names.
If you want to make sure that the reader understands that some method is going to take longer than just a simple getter, prefix it with a meaningful verb such as ``compute_...``, ``collect_...`` or ``retrieve_...``.

Property Names
--------------
Do not duplicate module (package) or class names in the property names.

For example, if you have a class called ``Features``, and want to add property to hold feature names, call the property simply ``names`` and not ``feature_names``.
The caller code would otherwise redundantly read ``Features.feature_names`` or ``features.feature_names``.

Module Names
------------
Do not call your modules, classes or functions ``..._helpers`` or ``..._utils``.
A general name is most probably an indicator that there is either a flaw in the design (*e.g.*, tight coupling which should be decoupled) or that there needs to be more thought spent on the naming.

If you have shared functionality in a module used by all or most of the submodules, put it in ``common`` submodule.

Programming Paradigm
--------------------
* Prefer functional programming to object-oriented programming.
    * Better be explicit about the data flow than implicit.
* Prefer namespaced functions in a (sub)module instead of class methods.
    * Side effects are difficult to trace.
    * Context of a function is immediately visible when you look at arguments.
      A function is much easier to isolate and unit test than a class method.
* Use inheritance only when you need polymorphism.
    * Do not use inheritance to share implementation; use namespaced functions for that.
    * Prefer simplicity with a small number of classes; see http://thedailywtf.com/articles/Enterprise-Dependency-The-Next-Generation
    * Use stateful objects in moderation.
    * Some thoughts: https://medium.com/@cscalfani/goodbye-object-oriented-programming-a59cda4c0e53

Anti-patterns from Clean Code
-----------------------------
Do not split script-like parts of the code into small chunks of one-time usage functions.

Use comments or regions to give overview.

It's ok to have long scripts that are usually more readable than a patchwork of small functions.
Jumping around a file while keeping the context in head is difficult and error-prone.

No Stateful Singletons
----------------------
Do not *ever* use stateful singletons.
Pass objects down the calling stack even if it seems tedious at first.

Imports
-------
Very common symbols such as ``Error`` or ``Identifier`` can be imported without prefix.
Usually, these symbols reside in ``aas_core_codegen.common``.

In addition, do not prefix ``typing`` symbols such as ``List`` or ``Mapping``, and the assertion functions from `icontract`_ design-by-contract library (see below).
Otherwise, the code would be completely unreadable.

All other symbols should be imported with an aliased prefix corresponding to the module.
For example:

.. code-block::python

    from aas_core_codegen.golang import (
        common as golang_common,
        naming as golang_naming
    )

The indention constants (``I``, ``II`` *etc.*) are the only aliases allowed for symbols.
No other symbol should be aliased.

Filesystem
----------
Use ``pathlib``, not ``os.path``.

Design-by-contract
------------------
Use `design-by-contract`_ as much as possible.
We use `icontract`_ library.

.. _design-by-contract: https://en.wikipedia.org/wiki/Design_by_contract
.. _icontract: https://icontract.readthedocs.io/

``Final`` and Constant Containers
---------------------------------
Prefer immutable to mutable objects and structures.

Distinguish between internally and externally mutable structures.
Annotate for immutability if the structures are only internally mutable.

For example, ``aas_core_codegen.intermediate._types`` are all marked as immutable since they should not be mutated *after* the intermediate translation phase.
They are, however, mutated within ``aas_core_codegen.intermediate._translate``.

Avoid Double-Asterisk (``**``) Operator
---------------------------------------
Double-asterisks are unpredictable for the reader, as all the keys need to be kept in mind, and overridden keys are simply ignored.

Please do not use ``**`` operator unless it is utterly necessary, and explain in the comment why it is necessary.
Check for overwriting keys where appropriate.

Classes over ``TypedDict``
---------------------------
Always use classes in the code.

Use ``TypedDict`` only if you have to deal with serialization (*e.g.*, to JSON).

Code Regions
------------
We intensively use PyCharms ``# region ...`` and ``# endregion`` to structure code into regions.

Comments
--------
Mark notes with ``# NOTE ({github username}):``.

Do not date the notes.
The notes need to be adapted as the code around them changes, so the date quickly
becomes misleading.

No ``# TODO`` in the code, please.

Comment only where the comments really add information.
Do not write self-evident comments.

Comments should be in proper English.
Write in simple present tense; avoid imperative mood.

Be careful about the capitals.
Start the sentence with a capital.
If you list bullet points, start with a capital, and do not forget conjectures:

.. code-block:: python

    #    * We ...,
    #    * Then, ..., and finally
    #    * We ...

The abbreviations are to be written properly in capitals (*e.g.*, ``JSON`` and not ``json``).

No code is allowed in the comments since it always rots.

Docstrings
----------
You can write full-blown Sphinx docstrings, if you wish.

In many cases, a short docstring is enough.
We are not religious about ``:param ...:`` and ``:return`` fields.

Follow `PEP 287`_.
Use imperative mood in the docstrings.

.. _PEP 287: https://peps.python.org/pep-0287/

Testing
-------
Write unit tests for everything that can be obviously tested at the function/class level.

For many inter-dependent code regions, writing unit tests is too tedious or nigh impossible to later maintain.
For such parts of the system, prefer integration tests with comparisons against initially recorded and reviewed golden data.
See, for example, ``dev/tests/csharp/test_main.py`` or ``dev/tests/intermediate/test_translate.py``.

The golden test data resides in ``dev/test_data/``.
The structure of the test data directory follows in general the test module structure.

Pre-commit Checks
=================

We provide a battery of pre-commit checks to make the code uniform and consistent across the code base.

We use `black`_ to format the code and use the default maximum line length of 88 characters.

.. _black: https://pypi.org/project/black/

To run all pre-commit checks, run from the root directory:

.. code-block::

    python continuous_integration/precommit.py

You can automatically re-format the code and fix certain files automatically with:

.. code-block::

    python continuous_integration/precommit.py --overwrite

The pre-commit script also runs as part of our continuous integration pipeline.

Write Commit Message
====================

We follow Chris Beams' `guidelines on commit messages`_:

1) Separate subject from body with a blank line
2) Limit the subject line to 50 characters
3) Capitalize the subject line
4) Do not end the subject line with a period
5) Use the imperative mood in the subject line, full sentences in the body
6) Wrap the body at 72 characters
7) Use the body to explain *what* and *why* vs. *how*

.. _guidelines on commit messages: https://chris.beams.io/posts/git-commit/

If you are merging in a pull request, please squash before merging.
We want to keep the Git history as simple as possible, and the commits during the development are rarely insightful later.

