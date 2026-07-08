# Write your solution here

#define user inputs
#word one
first_word = str(input("Please type in the 1st word:"))

#word two
second_word = str(input("Please type in the 2nd word:"))

#check order
if first_word < second_word:
    print(f"{second_word} comes alphabetically last.")
elif first_word > second_word:
    print(f"{first_word} comes alphabetically last.")
else:
    print("You gave the same word twice.")