# Write your solution here

#user input strings
user_phrase_one = str(input("Please type in string 1:"))
user_phrase_two = str(input("Please type in string 2:"))
len_one = len(user_phrase_one)
len_two = len(user_phrase_two)

#conditional check for length
if len_one > len_two :
    print(f"{user_phrase_one} is longer")
elif len_two > len_one:
    print(f"{user_phrase_two} is longer")
else:
    print("The strings are equally long")