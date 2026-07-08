# Fix the program
#user input
points = int(input("How many points are on your card? "))
original_points = points

#conditionals
if original_points < 100:
    points *= 1.1
    print("Your bonus is 10 %")

if original_points >= 100:
    points *= 1.15
    print("Your bonus is 15 %")

print("You now have", points, "points")