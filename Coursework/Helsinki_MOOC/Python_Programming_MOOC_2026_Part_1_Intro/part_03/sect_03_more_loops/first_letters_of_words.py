# Write your solution here

user_sentence = str(input("Please type in a sentence:"))

index = 0

while index < len(user_sentence):
    if index == 0 :
        print(user_sentence[index])
    if user_sentence[index-1] == " " :
        print(user_sentence[index])
    index += 1
