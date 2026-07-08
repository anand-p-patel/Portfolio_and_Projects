# Write your solution here

#define inputs
num1 = int(input("Number 1: "))
num2 = int(input("Number 2: "))
operation_choice = input("Operation: ")

if operation_choice == "add":
    print(f"{num1} + {num2} = {num1 + num2}")

if operation_choice == "multiply":
    print(f"{num1} * {num2} = {num1 * num2}")

if operation_choice == "subtract":
    print(f"{num1} - {num2} = {num1 - num2}")