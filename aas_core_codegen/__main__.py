# SPDX-FileCopyrightText: 2023 aas-core-codegen AUTHORS
#
# SPDX-License-Identifier: MIT

"""Run aas-core-codegen as Python module."""

import aas_core_codegen.main

if __name__ == "__main__":
    # The ``prog`` needs to be set in the argparse.
    # Otherwise, the program name in the help shown to the user will be ``__main__``.
    aas_core_codegen.main.main(prog="aas_core_codegen")
