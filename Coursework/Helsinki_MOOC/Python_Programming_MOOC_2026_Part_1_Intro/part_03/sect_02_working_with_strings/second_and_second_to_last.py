# Write your solution here

#user input
user_word = str(input("Please type in a string:"))

#define 2nd and 2nd to last letter
second_letter = user_word[1]
last_letter = user_word[-2]

if second_letter == last_letter :
    print(f"The second and the second to last characters are {second_letter}")
else:
    print("The second and the second to last characters are different")