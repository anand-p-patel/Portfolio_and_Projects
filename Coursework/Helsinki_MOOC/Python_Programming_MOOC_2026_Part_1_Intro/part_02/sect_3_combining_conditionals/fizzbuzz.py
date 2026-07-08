# Write your solution here

#define user input
user_number = int(input("Number:"))

#check if divisible
three = user_number % 3
five = user_number % 5

if three == 0 and five == 0:
    print("FizzBuzz")
elif three == 0:
    print("Fizz")
elif five == 0:
    print("Buzz")