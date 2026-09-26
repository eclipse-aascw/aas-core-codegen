@verification
def some_func(numbers: List[int], texts: List[str]) -> bool:
    for number, text in zip(numbers, texts):
        return number > 0

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
