if (color_.has_value()) {
  return *color_;
}

return fallback.has_value() ? *fallback : Color::kRed;
