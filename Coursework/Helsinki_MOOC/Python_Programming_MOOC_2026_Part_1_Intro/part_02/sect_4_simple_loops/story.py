# Write your solution here

user_word = ""
story = ""
repeat_word = ""

while True:
    user_word = str(input("Please type in a word:"))
    if user_word == "end":
        break
    if repeat_word == user_word:
        break
    story += user_word + " "
    repeat_word = user_word
print(f"{story}")