# Copy here code of line function from previous exercise
# def hash(number, word_input):
#     if len(word_input) == 0:
#         character = "*"
#     else:
#         character = word_input[0]
#     if character == " ":
#         character = "*"
#  
#
# def square_of_hashes(size):
#     # You should call function line here with proper parameters
#     # square is equal sides
#     # size is the number of lines and the number of characters in each line
#     index = 0
#     while index < size:
#         hash(size, "#")
#         index += 1


def hash(number, word_input):
    if len(word_input) == 0:
        character = "*"
    else:
        character = word_input[0]
    if character == " ":
        character = "*"

    print(character * number)


def square_of_hashes(size):
    # You should call function line here with proper parameters
    # square is equal sides
    # size is the number of lines and the number of characters in each line
    index = 0
    while index < size:
        hash(size, "#")
        index += 1

# You can test your function by calling it within the following block
if __name__ == "__main__":
    square_of_hashes(5)
