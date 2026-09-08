"""Run integration tests on the TypeScript generated code."""

import argparse
import contextlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Pattern

from aas_core_codegen.common import Stripped
from aas_core_codegen.typescript import common as typescript_common

from live_tests import common as live_tests_common


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output_dir",
        help=(
            "Path to where all the assembled project data including the test data "
            "should be copied to. If not specified, everything will be put into "
            "a temporary directory and deleted after the test."
        ),
    )
    parser.add_argument(
        "--select",
        help="Run only the test cases which match the regular expression",
        type=str,
    )
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir) if args.output_dir is not None else None

    select_text = str(args.select) if args.select is not None else None

    select: Optional[Pattern[str]] = None
    if select_text is not None:
        try:
            select = re.compile(select_text)
        except Exception as exception:
            print(f"Problems with --select {select_text}: {exception}", file=sys.stderr)
            return 1

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

    with contextlib.ExitStack() as exit_stack:
        # pylint: disable=consider-using-with

        if output_dir is None:
            temp_dir = tempfile.TemporaryDirectory()
            exit_stack.push(temp_dir)
            output_dir = pathlib.Path(temp_dir.name)
        else:
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exception:
                print(
                    f"Problems with --output_dir {output_dir}: {exception}",
                    file=sys.stderr,
                )
                return 1

        for case_dir in sorted(
            path for path in main_typescript_expected_dir.iterdir() if path.is_dir()
        ):
            if select is not None and select.match(case_dir.name) is None:
                print(f"Skipping {case_dir.name} since not selected.")
                continue

            print(f"Running the live test on {case_dir.name} ...")

            project_dir = output_dir / case_dir.name
            project_dir.mkdir(exist_ok=True)

            package_identifier = Stripped(
                (case_dir / "input" / "snippets" / "package_identifier.txt")
                .read_text(encoding="utf-8")
                .strip()
            )

            expected_output_dir = case_dir / "expected_output"

            print(
                f"Copying all the files from {expected_output_dir} to {project_dir} ..."
            )
            for path in sorted(
                path
                for path in expected_output_dir.glob("**/*")
                if path.name != "stdout.txt" and path.is_file()
            ):
                target_path = project_dir / (path.relative_to(expected_output_dir))

                # NOTE (mristin):
                # We check whether there is a change to avoid unnecessary actions
                # due to modification timestamps of the files.

                if not target_path.exists() or target_path.read_text(
                    encoding="utf-8"
                ) != path.read_text(encoding="utf-8"):
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(path, target_path)

            print(
                "We remove test/*.spec.ts files which contain no tests "
                "since eslint and jest will complain..."
            )
            for pth in sorted((project_dir / "test").glob("*.spec.ts")):
                text = pth.read_text(encoding="utf-8")
                if "test(" not in text:
                    pth.unlink()

            env_var_prefix = typescript_common.environment_variable_prefix(
                package_identifier
            )

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
  "devDependencies": {{
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
            # "varsIgnorePattern": "^(_|Aas.*)$"
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
        "varsIgnorePattern": "^(_|Aas.*|.*FromJsonable|.*FromXmlElement|parse.*|serialize.*|check.*|write.*|next.*)$",
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

            for cmd in [
                ["npm", "install"],
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
