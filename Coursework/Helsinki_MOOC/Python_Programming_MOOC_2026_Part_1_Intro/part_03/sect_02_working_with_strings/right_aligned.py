# Write your solution here

#20 - len(string) = number of * to be printed

#user defined string
user_word = str(input("Please type in a string:"))
row = "*"
length_of_asterisk = 20 - len(user_word)

print(row*length_of_asterisk + user_word)