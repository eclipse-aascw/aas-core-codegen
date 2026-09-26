@verification
def some_func(numbers: List[int]) -> bool:
    for i in range(len(numbers)):
        return numbers[i] > 0

    return True


__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"
