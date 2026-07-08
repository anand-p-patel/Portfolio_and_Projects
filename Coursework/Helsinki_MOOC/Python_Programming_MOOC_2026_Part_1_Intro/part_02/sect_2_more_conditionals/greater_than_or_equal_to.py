# Write your solution here

#define user inputs
user_input_one = int(input("Please type in the first number:"))
user_input_two = int(input("Please type in another number:"))

#conditional checks for value
if user_input_one > user_input_two:
    print(f"The greater number was: {user_input_one}")
elif user_input_one < user_input_two:
    print(f"The greater number was: {user_input_two}")
else:
    print("The numbers are equal!")