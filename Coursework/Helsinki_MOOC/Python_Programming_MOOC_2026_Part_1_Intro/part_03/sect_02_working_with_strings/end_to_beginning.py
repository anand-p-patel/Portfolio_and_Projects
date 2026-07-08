# Write your solution here
#user defined string
user_string = str(input("Please type in a string:"))
letter_placement = -1

while letter_placement >= -len(user_string) :
    print(user_string[(letter_placement)])
    letter_placement -=1