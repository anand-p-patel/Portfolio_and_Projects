# Write your solution here

#user word
user_word = str(input("Please type in a string:"))
letter_placement = -1
while letter_placement >= -len(user_word):
    print(user_word[letter_placement:])
    letter_placement -=1