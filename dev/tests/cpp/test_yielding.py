# pylint: disable=missing-docstring

import unittest

from aas_core_codegen.common import Identifier
from aas_core_codegen.yielding import (
    flow as yielding_flow,
)
from aas_core_codegen.cpp import yielding as cpp_yielding


class TestExecuteBody(unittest.TestCase):
    def test_empty(self) -> None:
        code = cpp_yielding.generate_execute_body(
            flow=[], state_member=Identifier("state_")
        )
        self.assertEqual("// Intentionally empty.", code)

    def test_inspired_by_verificator(self) -> None:
        # NOTE (mristin):
        # We test inspired by a real-world example from C++ code generation so that
        # we can check whether the resulting code is readable.
        #
        # Hence, we test with two invariants and two constrained primitive properties
        # so that the example is complex enough.
        code = cpp_yielding.generate_execute_body(
            flow=[
                yielding_flow.IfFalse(
                    condition="CheckInvariant0()",
                    body=[
                        yielding_flow.command_from_text(
                            "error_ = ErrorForInvariant0();"
                        ),
                        yielding_flow.Yield(),
                    ],
                ),
                yielding_flow.IfFalse(
                    condition="CheckInvariant1()",
                    body=[
                        yielding_flow.command_from_text(
                            "error_ = ErrorForInvariant1();"
                        ),
                        yielding_flow.Yield(),
                    ],
                ),
                yielding_flow.IfTrue(
                    condition="instance_.prop0.HasValue()",
                    body=[
                        yielding_flow.command_from_text(
                            """\
verification = VerifyConstrainedPrimitive(instance_.prop0.Value());
iterator_ = verification.Begin();
iterator_end_ = verification.End();"""
                        ),
                        yielding_flow.For(
                            condition="iterator_ != iterator_end_",
                            iteration="++iterator_",
                            body=[
                                yielding_flow.command_from_text("error_ = *iterator_;"),
                                yielding_flow.Yield(),
                            ],
                        ),
                        yielding_flow.command_from_text(
                            """\
iterator_.reset();
iterator_end_.reset();"""
                        ),
                    ],
                ),
                yielding_flow.IfTrue(
                    condition="instance_.prop1.HasValue()",
                    body=[
                        yielding_flow.command_from_text(
                            """\
verification = VerifyConstrainedPrimitive(instance_.prop1.Value());
iterator_ = verification.Begin();
iterator_end_ = verification.End();"""
                        ),
                        yielding_flow.For(
                            condition="iterator_ != iterator_end_",
                            iteration="++iterator_",
                            body=[
                                yielding_flow.command_from_text("error_ = *iterator_;"),
                                yielding_flow.Yield(),
                            ],
                        ),
                        yielding_flow.command_from_text(
                            """\
iterator_.reset();
iterator_end_.reset();"""
                        ),
                    ],
                ),
                yielding_flow.command_from_text(
                    """\
error_.Reset();
Finalize();"""
                ),
            ],
            state_member=Identifier("state_"),
        )

        self.maxDiff = None
        self.assertEqual(
            """\
while (true) {
  switch (state_) {
    case 0: {
      if (CheckInvariant0()) {
        state_ = 1;
        continue;
      }

      error_ = ErrorForInvariant0();

      state_ = 1;
      return;
    }

    case 1: {
      if (CheckInvariant1()) {
        state_ = 2;
        continue;
      }

      error_ = ErrorForInvariant1();

      state_ = 2;
      return;
    }

    case 2: {
      if (!(instance_.prop0.HasValue())) {
        state_ = 6;
        continue;
      }

      verification = VerifyConstrainedPrimitive(instance_.prop0.Value());
      iterator_ = verification.Begin();
      iterator_end_ = verification.End();
    }

    case 3: {
      if (!(iterator_ != iterator_end_)) {
        state_ = 5;
        continue;
      }

      error_ = *iterator_;

      state_ = 4;
      return;
    }

    case 4: {
      ++iterator_

      state_ = 3;
      continue;
    }

    case 5: {
      iterator_.reset();
      iterator_end_.reset();
    }

    case 6: {
      if (!(instance_.prop1.HasValue())) {
        state_ = 10;
        continue;
      }

      verification = VerifyConstrainedPrimitive(instance_.prop1.Value());
      iterator_ = verification.Begin();
      iterator_end_ = verification.End();
    }

    case 7: {
      if (!(iterator_ != iterator_end_)) {
        state_ = 9;
        continue;
      }

      error_ = *iterator_;

      state_ = 8;
      return;
    }

    case 8: {
      ++iterator_

      state_ = 7;
      continue;
    }

    case 9: {
      iterator_.reset();
      iterator_end_.reset();
    }

    case 10: {
      error_.Reset();
      Finalize();

      // We invalidate the state since we reached the end of the routine.
      state_ = 11;
      return;
    }

    default:
      throw std::logic_error(
        common::Concat(
          "Invalid state_: ",
          std::to_string(state_)
        )
      );
  }
}""",
            code,
        )


if __name__ == "__main__":
    unittest.main()
