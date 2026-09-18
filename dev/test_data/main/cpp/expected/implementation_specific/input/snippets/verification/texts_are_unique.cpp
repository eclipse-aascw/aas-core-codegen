bool TextsAreUnique(
  const std::vector<std::wstring>& texts
) {
  std::set<std::wstring> text_set;

  for (const std::wstring& text : texts) {
    if (text_set.find(text) != text_set.end()) {
      return false;
    }

    text_set.insert(text);
  }

  return true;
}
