# Copy here code of line function from previous exercise
def hash(number, word_input):
    if len(word_input) == 0:
        character = "*"
    else:
        character = word_input[0]
    if character == " ":
        character = "*"

    print(character * number)

def triangle(size):
    # You should call function line here with proper parameters
    #how to print a triangle of hashes?
    # the first line has 1 hash, the second line has 2 hashes, the third line has 3 hashes and so on
    # the number of hashes in each line is equal to the line number
    #multiply the line number by the character to get the number of characters in each line
    index = 0
    while index < size:
        hash(index + 1, "#")
        index += 1

# You can test your function by calling it within the following block
if __name__ == "__main__":
    triangle(5)
