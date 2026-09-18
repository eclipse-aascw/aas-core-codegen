bool ItemsHaveUniqueLabels(
  const std::vector<
    std::shared_ptr<types::IItem>
  >& items
) {
  std::set<std::wstring> label_set;

  for (const std::shared_ptr<types::IItem>& item : items) {
    const std::wstring& label = item->label();

    if (label_set.find(label) != label_set.end()) {
      return false;
    }

    label_set.insert(label);
  }

  return true;
}
