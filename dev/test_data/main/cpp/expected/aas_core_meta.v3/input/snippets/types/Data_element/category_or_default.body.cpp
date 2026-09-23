std::wstring result = category_.value_or(L"VARIABLE");

#ifdef DEBUG
if (
  constants::kValidCategoriesForDataElement.find(result)
  == constants::kValidCategoriesForDataElement.end()
) {
  std::wstringstream wss;
  wss
    << L"Unexpected default category: "
    << result;

  throw std::logic_error(
    common::WstringToUtf8(wss.str())
  );
}
#endif

return result;
