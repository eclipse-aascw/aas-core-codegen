bool HasBalancedBrackets(
  const std::wstring& text
) {
  int depth = 0;

  for (const wchar_t character : text) {
    if (character == L'[') {
      ++depth;
    } else if (character == L']') {
      --depth;
      if (depth < 0) {
        return false;
      }
    }
  }

  return depth == 0;
}
