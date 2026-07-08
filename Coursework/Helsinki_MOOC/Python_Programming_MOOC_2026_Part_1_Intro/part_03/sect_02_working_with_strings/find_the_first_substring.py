# Write your solution here

while True:
    #user inputs
    user_word = str(input("Please type in a word:"))
    user_substring = str(input("Please type in a character:"))
    #define character placement
    index = user_word.find(user_substring)
    #define print statement with conditional
    if index + 3 <= len(user_word):
        print(user_word[index:index+3])
    else:
        #break loop
        break
    break