# Copy here code of line function from previous exercise
def hash(number, word_input):
    if len(word_input) == 0:
        character = "*"
    else:
        character = word_input[0]
    if character == " ":
        character = "*"

    print(character * number)

def square(size, character):
    # You should call function line here with proper parameters
    index = 0
    while index < size:
        hash(size, character)
        index += 1

# You can test your function by calling it within the following block
if __name__ == "__main__":
    square(5, "x")