# pylint: disable=missing-docstring

import unittest

from aas_core_codegen.yielding import (
    flow as yielding_flow,
    linear as yielding_linear,
)


class TestLinearization(unittest.TestCase):
    def test_empty(self) -> None:
        statements = yielding_linear._linearize_control_flow(flow=[])

        dump = yielding_linear.dump(statements)
        self.assertEqual("", dump)

    def test_command(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[yielding_flow.command_from_text("DoSomething()")]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: DoSomething()""",
            dump,
        )

    def test_yield(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[yielding_flow.Yield()]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual("0: yield", dump)

    def test_simple_if_true_else(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfTrue(
                    condition="CheckSomething()",
                    body=[yielding_flow.command_from_text("DoSomething()")],
                    or_else=[yielding_flow.command_from_text("DoSomethingElse()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: if CheckSomething()
   is false, jump to 3
1: DoSomething()
2: jump 4
3: DoSomethingElse()
4: noop
5: Finalize()""",
            dump,
        )

    def test_simple_if_true_without_else(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfTrue(
                    condition="CheckSomething()",
                    body=[yielding_flow.command_from_text("DoSomething()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: if CheckSomething()
   is false, jump to 2
1: DoSomething()
2: noop
3: Finalize()""",
            dump,
        )

    def test_nested_if_true(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfTrue(
                    condition="CheckOuter()",
                    body=[
                        yielding_flow.IfTrue(
                            condition="OuterTrue_CheckInner()",
                            body=[
                                yielding_flow.command_from_text("OuterTrue_DoInner()")
                            ],
                            or_else=[
                                yielding_flow.command_from_text(
                                    "OuterTrue_DoElseInner()"
                                )
                            ],
                        )
                    ],
                    or_else=[
                        yielding_flow.IfTrue(
                            condition="OuterFalse_CheckInner()",
                            body=[
                                yielding_flow.command_from_text("OuterFalse_DoInner()")
                            ],
                            or_else=[
                                yielding_flow.command_from_text(
                                    "OuterFalse_DoElseInner()"
                                )
                            ],
                        )
                    ],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
 0: if CheckOuter()
    is false, jump to 7
 1: if OuterTrue_CheckInner()
    is false, jump to 4
 2: OuterTrue_DoInner()
 3: jump 5
 4: OuterTrue_DoElseInner()
 5: noop
 6: jump 12
 7: if OuterFalse_CheckInner()
    is false, jump to 10
 8: OuterFalse_DoInner()
 9: jump 11
10: OuterFalse_DoElseInner()
11: noop
12: noop
13: Finalize()""",
            dump,
        )

    def test_simple_if_false_else(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfFalse(
                    condition="CheckSomething()",
                    body=[yielding_flow.command_from_text("DoSinceCheckFalse()")],
                    or_else=[yielding_flow.command_from_text("DoSinceCheckTrue()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: if CheckSomething()
   is true, jump to 3
1: DoSinceCheckFalse()
2: jump 4
3: DoSinceCheckTrue()
4: noop
5: Finalize()""",
            dump,
        )

    def test_simple_if_false_without_else(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfFalse(
                    condition="CheckSomething()",
                    body=[yielding_flow.command_from_text("DoSinceCheckFalse()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: if CheckSomething()
   is true, jump to 2
1: DoSinceCheckFalse()
2: noop
3: Finalize()""",
            dump,
        )

    def test_for(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.For(
                    init="Start()",
                    condition="!Done()",
                    iteration="Next()",
                    body=[yielding_flow.command_from_text("DoSomething()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: Start()
1: if !Done()
   is false, jump to 5
2: DoSomething()
3: Next()
4: jump 1
5: noop
6: Finalize()""",
            dump,
        )

    def test_for_without_init(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.For(
                    condition="!Done()",
                    iteration="Next()",
                    body=[yielding_flow.command_from_text("DoSomething()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: if !Done()
   is false, jump to 4
1: DoSomething()
2: Next()
3: jump 0
4: noop
5: Finalize()""",
            dump,
        )

    def test_nested_if_in_for(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.For(
                    init="Start()",
                    condition="!Done()",
                    iteration="Next()",
                    body=[
                        yielding_flow.IfTrue(
                            condition="Check()",
                            body=[yielding_flow.command_from_text("DoSomething()")],
                        )
                    ],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: Start()
1: if !Done()
   is false, jump to 7
2: if Check()
   is false, jump to 4
3: DoSomething()
4: noop
5: Next()
6: jump 1
7: noop
8: Finalize()""",
            dump,
        )

    def test_while(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.While(
                    condition="!Done()",
                    body=[yielding_flow.command_from_text("DoSomething()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        dump = yielding_linear.dump(statements)
        self.assertEqual(
            """\
0: if !Done()
   is false, jump to 3
1: DoSomething()
2: jump 0
3: noop
4: Finalize()""",
            dump,
        )


class TestCompression(unittest.TestCase):
    def test_simple_if_else(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfTrue(
                    condition="CheckSomething()",
                    body=[yielding_flow.command_from_text("DoSomething()")],
                    or_else=[yielding_flow.command_from_text("DoSomethingElse()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        statements = yielding_linear._compress_in_place(statements)
        dump = yielding_linear.dump(statements)

        self.assertEqual(
            """\
 : if CheckSomething()
   is false, jump to 3
 : DoSomething()
 : jump 4
3: DoSomethingElse()
4: Finalize()""",
            dump,
        )

    def test_simple_if_without_else(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfTrue(
                    condition="CheckSomething()",
                    body=[yielding_flow.command_from_text("DoSomething()")],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        statements = yielding_linear._compress_in_place(statements)
        dump = yielding_linear.dump(statements)

        self.assertEqual(
            """\
 : if CheckSomething()
   is false, jump to 2
 : DoSomething()
2: Finalize()""",
            dump,
        )

    def test_nested_if(self) -> None:
        statements = yielding_linear._linearize_control_flow(
            flow=[
                yielding_flow.IfTrue(
                    condition="CheckOuter()",
                    body=[
                        yielding_flow.IfTrue(
                            condition="OuterTrue_CheckInner()",
                            body=[
                                yielding_flow.command_from_text("OuterTrue_DoInner()")
                            ],
                            or_else=[
                                yielding_flow.command_from_text(
                                    "OuterTrue_DoElseInner()"
                                )
                            ],
                        )
                    ],
                    or_else=[
                        yielding_flow.IfTrue(
                            condition="OuterFalse_CheckInner()",
                            body=[
                                yielding_flow.command_from_text("OuterFalse_DoInner()")
                            ],
                            or_else=[
                                yielding_flow.command_from_text(
                                    "OuterFalse_DoElseInner()"
                                )
                            ],
                        )
                    ],
                ),
                yielding_flow.command_from_text("Finalize()"),
            ]
        )

        statements = yielding_linear._compress_in_place(statements)
        dump = yielding_linear.dump(statements)

        self.assertEqual(
            """\
  : if CheckOuter()
    is false, jump to 7
  : if OuterTrue_CheckInner()
    is false, jump to 4
  : OuterTrue_DoInner()
  : jump 5
 4: OuterTrue_DoElseInner()
 5: jump 11
 7: if OuterFalse_CheckInner()
    is false, jump to 10
  : OuterFalse_DoInner()
  : jump 11
10: OuterFalse_DoElseInner()
11: Finalize()""",
            dump,
        )


class TestLinearizeToSubroutines(unittest.TestCase):
    def test_empty(self) -> None:
        result = yielding_linear.linearize_to_subroutines(flow=[])
        self.assertListEqual([], result)

    def test_inspired_by_verificator_in_cpp(self) -> None:
        # NOTE (mristin):
        # We test inspired by a real-world example from C++ code generation so that
        # we can see if it works, estimate how ergonomic it is to write the flows, and
        # check whether the resulting code is readable.
        #
        # Hence, we test with two invariants and two constrained primitive properties
        # so that all the above can be tested.
        subroutines = yielding_linear.linearize_to_subroutines(
            flow=[
                yielding_flow.IfTrue(
                    condition="Invariant0Invalidated",
                    body=[
                        yielding_flow.command_from_text(
                            "error_ = ErrorForInvariant0()"
                        ),
                        yielding_flow.Yield(),
                    ],
                ),
                yielding_flow.IfTrue(
                    condition="Invariant1Invalidated",
                    body=[
                        yielding_flow.command_from_text(
                            "error_ = ErrorForInvariant1()"
                        ),
                        yielding_flow.Yield(),
                    ],
                ),
                yielding_flow.IfTrue(
                    condition="instance_.prop0.HasValue()",
                    body=[
                        yielding_flow.command_from_text(
                            """\
verification = VerifyConstrainedPrimitive(instance_.prop0.Value())
iterator_ = verification.Begin()
iterator_end_ = verification.End()"""
                        ),
                        yielding_flow.For(
                            condition="iterator_ != iterator_end_",
                            iteration="++iterator_",
                            body=[
                                yielding_flow.command_from_text("error_ = *iterator_"),
                                yielding_flow.Yield(),
                            ],
                        ),
                        yielding_flow.command_from_text(
                            """\
iterator_.reset()
iterator_end_.reset()"""
                        ),
                    ],
                ),
                yielding_flow.IfTrue(
                    condition="instance_.prop1.HasValue()",
                    body=[
                        yielding_flow.command_from_text(
                            """\
verification = VerifyConstrainedPrimitive(instance_.prop1.Value())
iterator_ = verification.Begin()
iterator_end_ = verification.End()"""
                        ),
                        yielding_flow.For(
                            condition="iterator_ != iterator_end_",
                            iteration="++iterator_",
                            body=[
                                yielding_flow.command_from_text("error_ = *iterator_"),
                                yielding_flow.Yield(),
                            ],
                        ),
                        yielding_flow.command_from_text(
                            """\
iterator_.reset()
iterator_end_.reset()"""
                        ),
                    ],
                ),
                yielding_flow.command_from_text(
                    """\
error_.Reset()
Finalize()"""
                ),
            ]
        )

        output = "\n---\n".join(
            yielding_linear.dump(subroutine) for subroutine in subroutines
        )

        self.maxDiff = None
        self.assertEqual(
            """\
0: if Invariant0Invalidated
   is false, jump to 1
 : error_ = ErrorForInvariant0()
 : yield
---
1: if Invariant1Invalidated
   is false, jump to 2
 : error_ = ErrorForInvariant1()
 : yield
---
2: if instance_.prop0.HasValue()
   is false, jump to 6
 : verification = VerifyConstrainedPrimitive(instance_.prop0.Value())
   iterator_ = verification.Begin()
   iterator_end_ = verification.End()
---
3: if iterator_ != iterator_end_
   is false, jump to 5
 : error_ = *iterator_
 : yield
---
4: ++iterator_
 : jump 3
---
5: iterator_.reset()
   iterator_end_.reset()
---
6: if instance_.prop1.HasValue()
   is false, jump to 10
 : verification = VerifyConstrainedPrimitive(instance_.prop1.Value())
   iterator_ = verification.Begin()
   iterator_end_ = verification.End()
---
7: if iterator_ != iterator_end_
   is false, jump to 9
 : error_ = *iterator_
 : yield
---
8: ++iterator_
 : jump 7
---
9: iterator_.reset()
   iterator_end_.reset()
---
10: error_.Reset()
    Finalize()""",
            output,
        )


if __name__ == "__main__":
    unittest.main()
