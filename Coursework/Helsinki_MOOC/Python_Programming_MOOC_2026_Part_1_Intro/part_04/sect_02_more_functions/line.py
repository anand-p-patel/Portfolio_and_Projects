# Write your solution here
# You can test your function by calling it within the following block

# The function should print the given character as many times as specified by the number
# For example, the call line(5, "x") should print xxxxx
# The function should not return anything
# You can assume that the number will always be a positive integer and the character will always be a string of length 1


def line(number, word_input):
    # Original implementation:
    # character = word_input[0]
    # if character == " ":
    #     character = "*"
    #     print(character * number)
    # else:
    #     print(character * number)

    if len(word_input) == 0:
        character = "*"
    else:
        character = word_input[0]

    if character == " ":
        character = "*"

    print(character * number)


if __name__ == "__main__":
    line(5, "")
