import unittest

from aas_core_codegen.parse import retree as parse_retree
from aas_core_codegen.cpp.lib import _generate_pattern as cpp_lib_generate_pattern


class TestForRealWorldPatterns(unittest.TestCase):
    def test_for_xs_date_prefix(self) -> None:
        pattern = "^(-?[0-9]+)-(0[1-9]|1[0-2])-(0[0-9]|1[0-9]|2[0-9]|30|31).*$"

        regex, error = parse_retree.parse([pattern])
        assert error is None, f"{error=}"
        assert regex is not None

        code = cpp_lib_generate_pattern._generate_program_definition_for_regex(
            regex=regex
        )
        self.assertEqual(
            """\
std::vector<std::unique_ptr<revm::Instruction> > program;

{  // ^(-?[0-9]+)-(0[1-9]|1[0-2])-(0[0-9]|1[0-9]|2[0-9]|30|31).*$
  {  // -?[0-9]+
    {  // -?
      program.emplace_back(
        common::make_unique<revm::InstructionSplit>(1, 2)
      );
      // -
      program.emplace_back(  // 1
        common::make_unique<revm::InstructionChar>(L'-')
      );
    }  // -?
    {  // [0-9]+
      // [0-9]
      program.emplace_back(  // 2
        common::make_unique<revm::InstructionSet>(
          std::vector<revm::Range>{
            revm::Range(L'0', L'9')
          }
        )
      );
      program.emplace_back(
        common::make_unique<revm::InstructionSplit>(2, 4)
      );
    }  // [0-9]+
  }  // -?[0-9]+
  // -
  program.emplace_back(  // 4
    common::make_unique<revm::InstructionChar>(L'-')
  );
  {  // 0[1-9]|1[0-2]
    program.emplace_back(
      common::make_unique<revm::InstructionSplit>(6, 9)
    );
    {  // 0[1-9]
      // 0
      program.emplace_back(  // 6
        common::make_unique<revm::InstructionChar>(L'0')
      );
      // [1-9]
      program.emplace_back(
        common::make_unique<revm::InstructionSet>(
          std::vector<revm::Range>{
            revm::Range(L'1', L'9')
          }
        )
      );
    }  // 0[1-9]
    program.emplace_back(
      common::make_unique<revm::InstructionJump>(11)
    );
    {  // 1[0-2]
      // 1
      program.emplace_back(  // 9
        common::make_unique<revm::InstructionChar>(L'1')
      );
      // [0-2]
      program.emplace_back(
        common::make_unique<revm::InstructionSet>(
          std::vector<revm::Range>{
            revm::Range(L'0', L'2')
          }
        )
      );
    }  // 1[0-2]
  }  // 0[1-9]|1[0-2]
  // -
  program.emplace_back(  // 11
    common::make_unique<revm::InstructionChar>(L'-')
  );
  {  // 0[0-9]|1[0-9]|2[0-9]|30|31
    program.emplace_back(
      common::make_unique<revm::InstructionSplit>(13, 16)
    );
    {  // 0[0-9]
      // 0
      program.emplace_back(  // 13
        common::make_unique<revm::InstructionChar>(L'0')
      );
      // [0-9]
      program.emplace_back(
        common::make_unique<revm::InstructionSet>(
          std::vector<revm::Range>{
            revm::Range(L'0', L'9')
          }
        )
      );
    }  // 0[0-9]
    program.emplace_back(
      common::make_unique<revm::InstructionJump>(30)
    );
    program.emplace_back(  // 16
      common::make_unique<revm::InstructionSplit>(17, 20)
    );
    {  // 1[0-9]
      // 1
      program.emplace_back(  // 17
        common::make_unique<revm::InstructionChar>(L'1')
      );
      // [0-9]
      program.emplace_back(
        common::make_unique<revm::InstructionSet>(
          std::vector<revm::Range>{
            revm::Range(L'0', L'9')
          }
        )
      );
    }  // 1[0-9]
    program.emplace_back(
      common::make_unique<revm::InstructionJump>(30)
    );
    program.emplace_back(  // 20
      common::make_unique<revm::InstructionSplit>(21, 24)
    );
    {  // 2[0-9]
      // 2
      program.emplace_back(  // 21
        common::make_unique<revm::InstructionChar>(L'2')
      );
      // [0-9]
      program.emplace_back(
        common::make_unique<revm::InstructionSet>(
          std::vector<revm::Range>{
            revm::Range(L'0', L'9')
          }
        )
      );
    }  // 2[0-9]
    program.emplace_back(
      common::make_unique<revm::InstructionJump>(30)
    );
    program.emplace_back(  // 24
      common::make_unique<revm::InstructionSplit>(25, 28)
    );
    {  // 30
      // 3
      program.emplace_back(  // 25
        common::make_unique<revm::InstructionChar>(L'3')
      );
      // 0
      program.emplace_back(
        common::make_unique<revm::InstructionChar>(L'0')
      );
    }  // 30
    program.emplace_back(
      common::make_unique<revm::InstructionJump>(30)
    );
    {  // 31
      // 3
      program.emplace_back(  // 28
        common::make_unique<revm::InstructionChar>(L'3')
      );
      // 1
      program.emplace_back(
        common::make_unique<revm::InstructionChar>(L'1')
      );
    }  // 31
  }  // 0[0-9]|1[0-9]|2[0-9]|30|31
  program.emplace_back(  // 30
    common::make_unique<revm::InstructionMatch>()
  );
}  // ^(-?[0-9]+)-(0[1-9]|1[0-2])-(0[0-9]|1[0-9]|2[0-9]|30|31).*$""",
            code,
        )


if __name__ == "__main__":
    unittest.main()
