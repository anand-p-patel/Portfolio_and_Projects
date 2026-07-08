

def palindromes(string_one):
    reverse_string = string_one[::-1]
    if reverse_string != string_one:
        print("that wasn't a palindrome")
        return False
    else:
        print(f"{string_one} is a palindrome!")
        return True
        
while True:
    string_one = input("Please type in a palindrome: ")
    if palindromes(string_one):
        break
        

if __name__ == "__main__":
    palindromes(string_one)
