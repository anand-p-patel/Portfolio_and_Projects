# Write your solution here
number = int(input("Please type in a number:"))

#zero
if number == 0:
    print(f"The absolute value of this number is {number}")

#positive numbers
if number > 0:
    print(f"The absolute value of this number is {number}")

#negative numbers absolute value
if number < 0:
    abs_value = number * -1
    print(f"The absolute value of this number is {abs_value}")