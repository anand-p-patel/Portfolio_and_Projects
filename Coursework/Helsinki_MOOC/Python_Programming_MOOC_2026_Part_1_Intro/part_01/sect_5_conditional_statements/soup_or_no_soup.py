# Write your solution here
#define cost per portion
soup_portion_cost = 5.90

#input name
name = input("Please tell me your name:")

#jerry conditional
if name == "Jerry":
    print("Next please!")


#not jerry portion size and total cost
if name != "Jerry":
    portion_size = int(input("How many portions of soup?"))
    total_cost = portion_size * soup_portion_cost
    print(f"The total cost is {total_cost}")
    print("Next please!")