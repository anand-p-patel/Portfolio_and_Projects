# Write your solution here
#user inputs
user_word = str(input("Please type in a string:"))
user_substring = str(input("Please type in a substring:"))

#define two indexes
index_one = user_word.find(user_substring)

if index_one == -1 :
    print("The substring does not occur twice in the string.")
else:
    index_two = user_word.find(user_substring, index_one + len(user_substring))
    if index_two != -1 :
        print(f"The second occurrence of the substring is at index {index_two}.")
    else:
        print("The substring does not occur twice in the string.")
 