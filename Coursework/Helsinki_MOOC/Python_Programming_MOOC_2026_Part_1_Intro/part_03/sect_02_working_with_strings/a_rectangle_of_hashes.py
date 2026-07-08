# Write your solution here

# Write your solution here

#define user input
user_defined_width = int(input("Width:"))
user_defined_height = int(input("Height:"))
row = "#"


while user_defined_height > 0:
    print(row * user_defined_width)
    user_defined_height -= 1