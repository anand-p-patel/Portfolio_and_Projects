# Write your solution here

#user input
user_word = str(input("Word:"))
row = "*"
#define white space size
white_space = " "
length_word = len(user_word)
length_space = (28 - length_word) // 2

if (28 - length_word) % 2 == 0:
    print(row * 30)
    print(row + (white_space*length_space) + user_word + (white_space*length_space) + row)
    print(row * 30)
elif (28 - length_word) % 2 == 1 :
    print(row * 30)
    print(row + (white_space*length_space) + user_word + white_space * (length_space + 1) + row)
    print(row * 30)