"""Check that meta-data in ``pyproject.toml`` and ``__init__.py`` are consistent."""

import os.path
import pathlib
import sys
from typing import List

if sys.version_info >= (3, 11):
    import tomllib
else:
    # noinspection PyUnreachableCode
    import tomli as tomllib


def main() -> None:
    """Execute the main routine."""
    errors: List[str] = []

    repo_root = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent
    pyproject_toml_path = repo_root / "pyproject.toml"

    with pyproject_toml_path.open("rb") as f:
        pyproject_data = tomllib.load(f)

    # Get module name from [tool.setuptools.packages.find] include
    packages_find = (
        pyproject_data.get("tool", {})
        .get("setuptools", {})
        .get("packages", {})
        .get("find", {})
    )
    include_packages = packages_find.get("include", [])

    if len(include_packages) == 0:
        raise AssertionError(
            f"No packages found in [tool.setuptools.packages.find] include "
            f"in {pyproject_toml_path}"
        )

    # NOTE (mristin):
    # We assume that the first include package is the main one.
    module_name = include_packages[0]

    module = __import__(module_name)

    init_version = module.__version__
    pyproject_version = pyproject_data["project"]["version"]

    # NOTE (mristin):
    # We check for the version.
    if init_version != pyproject_version:
        errors.append(
            f"Version mismatch: __init__.py has {init_version!r}, "
            f"pyproject.toml has {pyproject_version!r}"
        )

    # NOTE (mristin):
    # We check for the authoers.
    init_authors = [author.strip() for author in module.__author__.split(",")]
    pyproject_authors = [
        author["name"] for author in pyproject_data["project"]["authors"]
    ]

    if init_authors != pyproject_authors:
        errors.append(
            f"Authors mismatch: __init__.py has {init_authors!r}, "
            f"pyproject.toml has {pyproject_authors!r}"
        )

    # NOTE (mristin):
    # We check for the development status.
    init_status = module.__status__
    pyproject_status = ""

    for classifier in pyproject_data["project"]["classifiers"]:
        if classifier.startswith("Development Status"):
            parts = classifier.split("::")

            if len(parts) >= 2:
                status = parts[1].strip()

                # NOTE (mristin):
                # We extract just the status part (*e.g.*, "5 - Production/Stable" ->
                # "Production/Stable").

                if " - " in status:
                    pyproject_status = status.split(" - ", 1)[1]
                else:
                    pyproject_status = status

                break

    if init_status != pyproject_status:
        errors.append(
            f"Status mismatch: __init__.py has {init_status!r}, "
            f"pyproject.toml classifiers have {pyproject_status!r}"
        )

    # NOTE (mristin):
    # We check for the license.
    init_license = module.__license__
    pyproject_license = ""

    for classifier in pyproject_data["project"]["classifiers"]:
        if classifier.startswith("License"):
            pyproject_license = classifier
            break

    if init_license != pyproject_license:
        errors.append(
            f"License mismatch: __init__.py has {init_license!r}, "
            f"pyproject.toml classifiers have {pyproject_license!r}"
        )

    if len(errors) > 0:
        errors_str = "\n".join(errors)
        print(f"Meta-data consistency check failed:\n{errors_str}", file=sys.stderr)
        sys.exit(1)

    print("All meta-data fields are consistent between __init__.py and pyproject.toml.")


if __name__ == "__main__":
    main()
