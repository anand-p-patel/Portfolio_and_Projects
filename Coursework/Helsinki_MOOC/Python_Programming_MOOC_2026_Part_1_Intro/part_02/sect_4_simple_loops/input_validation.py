from math import sqrt
# Write your solution here
while True:
    number_input = int(input("Please type in a number:"))
    if number_input == 0 :
        print("Exiting...")
        break
    if number_input < 0 :
        print("Invalid number")
    else:
        root = sqrt(number_input)
        print(+root)