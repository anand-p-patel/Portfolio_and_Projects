# Write your solution here

user_number = ""
amount_of_inputs = 0
user_sum = 0
positive_count = 0
negative_count = 0

print(f"Please type in integer numbers. Type in 0 to finish.")

while True:
    user_number = int(input("Number:"))
    if user_number != 0 and user_number > 0 :
        amount_of_inputs += 1
        positive_count += 1
        user_sum += user_number
    elif user_number != 0 and user_number < 0:
        amount_of_inputs +=1
        negative_count += 1
        user_sum += user_number
    elif user_number == 0 :
        break
if amount_of_inputs > 0:
    user_mean = float((user_sum) / (amount_of_inputs))
else:
    user_mean = 0

print("...the program asks for numbers")
print(f"Numbers typed in {amount_of_inputs}")
print(f"The sum of the numbers is {user_sum}")
print(f"The mean of the numbers is {user_mean}")
print(f"Positive numbers {positive_count}")
print(f"Negative numbers {negative_count}")