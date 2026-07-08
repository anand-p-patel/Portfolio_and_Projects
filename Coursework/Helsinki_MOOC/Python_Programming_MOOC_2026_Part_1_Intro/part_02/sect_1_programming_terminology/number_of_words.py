# Write your solution here
#define user input
user_word = input("Please type in a word:")

#define word length
word_length = len(user_word)

#conditional checks for length
if word_length <= 1:
    print("Thank you!")

#print statement otherwise
if word_length > 1:
    print(f"There are {word_length} letters in the word {user_word}")
    print("Thank you!")