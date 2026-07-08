# Write your solution here
# Write your solution here
import random
import string

def generate_strong_password(length, numbers, special_characters):
    char_pool = string.ascii_letters.lower()
    spc_char = "!?=+-()#"
    required = []
    if numbers:
        required.append(random.choice(string.digits))
        char_pool += string.digits
    if special_characters:
        required.append(random.choice(spc_char))
        char_pool += spc_char
    remaining = length - len(required)
    generated_pw = required + random.choices(char_pool, k = remaining)
    return ''.join(generated_pw)


if __name__ == "__main__":
    for i in range(10):
        print(generate_strong_password(5, True, True))