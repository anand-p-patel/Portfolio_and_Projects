# Write your solution here
#make a program with three functions: first_word, second_word, and last_word. Each function should take a string as a parameter and return the first, second, or last word of the string, respectively. You can assume that the string will always contain at least two words.
#how to detect first second and third word without using or find? Use the " " to detect the spaces between the words. The first word is the substring from the beginning of the string to the first space, the second word is the substring between the first and second space, and the last word is the substring from the last space to the end of the string. You can use string slicing to extract these substrings.
#print white space + 1 to white space - 1 for each word except the first and last word. For the first word, print from the beginning of the string to the first space. For the last word, print from the last space to the end of the string.
def first_word(string):
    return string[:string.find(" ")]

def second_word(string):
    first_space = string.find(" ")
    second_space = string.find(" ", first_space + 1)
    if second_space == -1:
        return string[first_space + 1:]
    # original line: return string[first_space + 1:second_space]
    return string[first_space + 1:second_space]

def last_word(string):
    return string[string.rfind(" ") + 1:]

# You can test your function by calling it within the following block
if __name__ == "__main__":
    sentence = "once upon a time there was a programmer"
    print(first_word(sentence))
    print(second_word(sentence))
    print(last_word(sentence))