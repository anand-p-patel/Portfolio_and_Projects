# Write your solution here

#define user inputs
user_word = str(input("Please type in a word:"))
user_character = str(input("Please type in a character"))


while True:
    index = user_word.find(user_character)
    if index + 3 > len(user_word) or index == -1 :
        break
    print(user_word[index:index+3])
    user_word = user_word[index+1:]
