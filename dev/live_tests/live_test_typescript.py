"""Run integration tests on the TypeScript generated code."""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, Pattern

from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common

from live_tests import common as live_tests_common


def install_dependencies(output_dir: pathlib.Path) -> None:
    """
    Install the dependencies shared by all the projects in ``output_dir``.

    All the projects have the same dependencies, so we install them only once
    in ``output_dir`` instead of in every project to save time and disk space.
    Both Node module resolution and ``npm run`` walk up the directory tree,
    so the projects in the sub-directories find the dependencies.
    """
    (output_dir / "package.json").write_text(
        """\
{
  "name": "live-tests",
  "private": true,
  "version": "0.0.1",
  "devDependencies": {
    "@babel/cli": "^7.20.7",
    "@babel/core": "^7.20.12",
    "@babel/parser": "^7.20.3",
    "@babel/preset-env": "^7.20.2",
    "@babel/preset-typescript": "^7.18.6",
    "@babel/types": "^7.20.2",
    "@rollup/plugin-babel": "^6.0.3",
    "@rollup/plugin-node-resolve": "^15.0.1",
    "@rollup/plugin-terser": "^0.3.0",
    "@types/jest": "^29.2.1",
    "@types/node": "^18.11.11",
    "@typescript-eslint/eslint-plugin": "^5.42.1",
    "@typescript-eslint/parser": "^5.42.1",
    "cross-env": "^7.0.3",
    "eslint": "^8.27.0",
    "eslint-config-prettier": "^8.5.0",
    "eslint-plugin-prettier": "^4.2.1",
    "jest": "^29.2.2",
    "prettier": "^2.7.1",
    "rimraf": "^4.1.1",
    "rollup": "^3.10.0",
    "ts-jest": "^29.0.3",
    "typedoc": "^0.23.22",
    "typescript": "^4.8.4",
    "xmlsax-typescript": "^1.0.0-rc.2",
    "@xmldom/xmldom": "^0.9.10"
  }
}
""",
        encoding="utf-8",
    )

    cmd = ["npm", "install", "--no-audit", "--no-fund"]
    print(f"Running {live_tests_common.escape_and_join_command(cmd)} in {output_dir}")
    subprocess.check_call(cmd, cwd=output_dir)


def prepare_project(case_dir: pathlib.Path, project_dir: pathlib.Path) -> Stripped:
    """
    Copy the generated code of the case to ``project_dir`` and set up the project.

    The dependencies need to be installed in the parent directory of ``project_dir``
    with :py:func:`install_dependencies`. Return the package identifier.
    """
    project_dir.mkdir(exist_ok=True)

    package_identifier = Stripped(
        (case_dir / "input" / "snippets" / "package_identifier.txt")
        .read_text(encoding="utf-8")
        .strip()
    )

    expected_output_dir = case_dir / "expected_output"

    live_tests_common.copy_expected_output(expected_output_dir, project_dir)

    print(
        "We remove test/*.spec.ts files which contain no tests "
        "since eslint and jest will complain..."
    )
    for pth in sorted((project_dir / "test").glob("*.spec.ts")):
        text = pth.read_text(encoding="utf-8")
        if "test(" not in text:
            pth.unlink()

    env_var_prefix = typescript_common.environment_variable_prefix(package_identifier)

    (project_dir / "package.json").write_text(
        f"""\
{{
  "name": "{package_identifier}",
  "private": true,
  "version": "0.0.1",
  "scripts": {{
    "build:esm": "cross-env BABEL_ENV=esmUnbundled babel src --extensions '.ts' --out-dir 'dist/lib/esm' --source-maps",
    "build:cjs": "cross-env BABEL_ENV=cjs babel src --extensions '.ts' --out-dir 'dist/lib/cjs' --source-maps",
    "build:bundles": "cross-env BABEL_ENV=esmBundled rollup -c",
    "build:declarations": "tsc -p tsconfig.json",
    "prebuild": "rimraf dist",
    "build": "npm run build:esm && npm run build:cjs && npm run build:bundles && npm run build:declarations",
    "lint": "eslint src test --ext .ts",
    "test": "{env_var_prefix}_TEST_DATA_DIR=./test_data jest --coverage",
    "format": "prettier --config .prettierrc 'src/**/*.ts' 'test/**/*.ts' --write"
  }},
  "main": "dist/lib/cjs/index.js",
  "module": "dist/lib/esm/index.js",
  "types": "dist/types/index.d.ts",
  "exports": {{
    ".": {{
      "require": "./dist/lib/cjs/index.js",
      "import": "./dist/lib/esm/index.js",
      "types": "./dist/types/index.d.ts"
    }},
    "./types": {{
      "require": "./dist/lib/cjs/types.js",
      "import": "./dist/lib/esm/types.js",
      "types": "./dist/types/types.d.ts"
    }},
    "./jsonization": {{
      "require": "./dist/lib/cjs/jsonization.js",
      "import": "./dist/lib/esm/jsonization.js",
      "types": "./dist/types/jsonization.d.ts"
    }},
    "./stringification": {{
      "require": "./dist/lib/cjs/stringification.js",
      "import": "./dist/lib/esm/stringification.js",
      "types": "./dist/types/stringification.d.ts"
    }},
    "./verification": {{
      "require": "./dist/lib/cjs/verification.js",
      "import": "./dist/lib/esm/verification.js",
      "types": "./dist/types/verification.d.ts"
    }}
  }},
  "typesVersions": {{
    "*": {{
      ".": [
        "./dist/types/index.d.ts"
      ],
      "types": [
        "./dist/types/types.d.ts"
      ],
      "jsonization": [
        "./dist/types/jsonization.d.ts"
      ],
      "stringification": [
        "./dist/types/stringification.d.ts"
      ],
      "verification": [
        "./dist/types/verification.d.ts"
      ]
    }}
  }},
  "files": [
    "dist"
  ],
  "publishConfig": {{
    "access": "public"
  }}
}}
""",
        encoding="utf-8",
    )

    (project_dir / ".prettierrc").write_text(
        """\
{
  "semi": true,
  "trailingComma": "none",
  "printWidth": 88
}
""",
        encoding="utf-8",
    )

    # NOTE (mristin):
    # We set:
    # "varsIgnorePattern": "^(_|Our.*)$"
    # in .eslintrc since we want to ignore unused imports.

    (project_dir / ".eslintrc").write_text(
        """\
{
  "root": true,
  "parser": "@typescript-eslint/parser",
  "plugins": [
    "@typescript-eslint",
    "prettier"
  ],
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/eslint-recommended",
    "plugin:@typescript-eslint/recommended",
    "prettier"
  ],
  "rules": {
    "no-console": 2,
    "prettier/prettier": 2,
    "no-constant-condition": [
      "error",
      {
        "checkLoops": false
      }
    ],
    // See: https://stackoverflow.com/a/64067915/1600678
    "no-unused-vars": "off",
    "@typescript-eslint/no-unused-vars": [
      "error",
      {
        "varsIgnorePattern": "^(_|Our.*|.*FromJsonable|.*FromXmlElement|parse.*|serialize.*|check.*|write.*|next.*)$",
        // NOTE (mristin):
        // We do not flag unused function/method parameters. Some
        // meta-model-defined functions (*e.g.*, a ``@verification`` function
        // which unconditionally returns ``True``) legitimately ignore one or
        // more of their parameters.
        "args": "none"
      }
    ]
  }
}
""",
        encoding="utf-8",
    )

    (project_dir / ".eslintignore").write_text(
        """\
node_modules
dist
""",
        encoding="utf-8",
    )

    (project_dir / ".babelrc.js").write_text(
        """\
const sharedPresets = ['@babel/typescript'];
const shared = {
  ignore: ['src/**/*.spec.ts'],
  presets: sharedPresets
}

module.exports = {
  env: {
    esmUnbundled: shared,
    esmBundled: {
      ...shared,
      presets: [['@babel/preset-env', {
        targets: "> 0.25%, not dead"
      }], ...sharedPresets],
    },
    cjs: {
      ...shared,
      presets: [['@babel/preset-env', {
        modules: 'commonjs'
      }], ...sharedPresets],
    },
    test: {
      presets: ['@babel/preset-env', ...sharedPresets]
    },
  }
}
"""
    )

    (project_dir / "rollup.config.mjs").write_text(
        """\
import babel from "@rollup/plugin-babel";
import resolve from "@rollup/plugin-node-resolve";
import terser from "@rollup/plugin-terser";

const extensions = [".js", ".ts"];

export default {
  input: "src/index.ts",
  output: [
    {
      file: "dist/bundles/bundle.esm.js",
      format: "esm",
      sourcemap: true
    },
    {
      file: "dist/bundles/bundle.esm.min.js",
      format: "esm",
      plugins: [terser()],
      sourcemap: true
    }
  ],
  plugins: [
    resolve({ extensions }),
    babel({
      babelHelpers: "bundled",
      include: ["src/**/*.ts"],
      extensions,
      exclude: "./node_modules/**"
    })
  ]
}"""
    )

    (project_dir / "tsconfig.json").write_text(
        """\
{
  "compilerOptions": {
    "module": "commonjs",
    "target": "es2015",
    "moduleResolution": "node",
    "emitDeclarationOnly": true,
    "declarationMap": true,
    "declaration": true,
    "lib": ["es2015"],
    "sourceMap": true,
    "outDir": "./dist/types",
    "esModuleInterop": true
  },
  "include": [
    "src/**/*"
  ]
}
""",
        encoding="utf-8",
    )

    (project_dir / "jest.config.js").write_text(
        """\
/** @type {import('ts-jest').JestConfigWithTsJest} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
};
""",
        encoding="utf-8",
    )

    return package_identifier


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    live_tests_common.add_output_dir_argument(parser)
    live_tests_common.add_select_argument(parser)
    args = parser.parse_args()

    select: Optional[Pattern[str]] = args.select

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    main_typescript_expected_dir = (
        repo_root / "dev" / "test_data" / "main" / "typescript" / "expected"
    )

    assert (
        main_typescript_expected_dir.exists() and main_typescript_expected_dir.is_dir()
    )

    live_tests_typescript_dir = (
        repo_root / "dev" / "test_data" / "live_tests" / "typescript"
    )

    with live_tests_common.open_output_dir(args.output_dir) as output_dir:
        install_dependencies(output_dir)

        for case_dir in live_tests_common.select_case_dirs(
            main_typescript_expected_dir, select
        ):
            print(f"Running the live test on {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            package_identifier = prepare_project(case_dir, project_dir)

            env_var_prefix = typescript_common.environment_variable_prefix(
                package_identifier
            )

            for cmd in [
                ["npm", "run", "format"],
                ["npm", "run", "lint"],
                ["npm", "run", "build"],
            ]:
                print(
                    f"Running {live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir)

            case_test_data_dir = live_tests_typescript_dir / "test_data" / case_dir.name

            if not case_test_data_dir.exists():
                # NOTE (mristin):
                # We fall back to the shared test data.
                case_test_data_dir = live_tests_common.common_test_data_dir_for_case(
                    case_name=case_dir.name
                )

            if case_test_data_dir.exists():
                target_test_data = project_dir / "test_data"

                print(
                    f"Copying test data from {case_test_data_dir} "
                    f"to {target_test_data} ..."
                )
                for pth in sorted(case_test_data_dir.glob("**/*")):
                    if not pth.is_file():
                        continue

                    target_pth = target_test_data / pth.relative_to(case_test_data_dir)

                    target_pth.parent.mkdir(exist_ok=True, parents=True)

                    shutil.copy(pth, target_pth)

                print("Running the tests...")
                cmd = ["npm", "run", "test"]

                env = os.environ.copy()

                env_var_test_record_mode = f"{env_var_prefix}_TEST_RECORD_MODE"
                env[env_var_test_record_mode] = "1"

                print(
                    f"Running "
                    f"{env_var_test_record_mode}"
                    f"={env.get(env_var_test_record_mode)} "
                    f"{live_tests_common.escape_and_join_command(cmd)} "
                    f"in {project_dir}"
                )
                subprocess.check_call(cmd, cwd=project_dir, env=env)

    return 0


if __name__ == "__main__":
    sys.exit(main())
