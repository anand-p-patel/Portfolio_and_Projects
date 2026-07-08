def change_case(orig_string: str) -> str:
    return orig_string.swapcase()


def split_in_half(orig_string: str) -> tuple:
    half = len(orig_string) // 2
    return orig_string[:half], orig_string[half:]


def remove_special_characters(orig_string: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")
    return ''.join(ch for ch in orig_string if ch in allowed)
