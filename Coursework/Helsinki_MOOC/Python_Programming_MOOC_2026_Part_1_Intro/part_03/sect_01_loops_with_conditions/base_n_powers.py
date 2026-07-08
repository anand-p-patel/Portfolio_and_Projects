# Write your solution here
#user input
upper_limit = int(input("Upper limit:"))
base_input = int(input("Base:"))

#define starting point
increasing_input = 1

while upper_limit >= increasing_input :
    print(increasing_input)
    increasing_input *= base_input
