# Write your solution here
import random
import string
def generate_password(length):
    char_pool = string.ascii_letters.lower()
    generated_pw = random.choices(char_pool, k = length)
    return ''.join(generated_pw)

