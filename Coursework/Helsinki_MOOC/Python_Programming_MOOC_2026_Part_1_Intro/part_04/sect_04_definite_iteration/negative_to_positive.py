# Write your solution here

user_input = int(input("Please type in a positive integer: "))

for i in range(user_input, 0, -1) :
    print(i * -1)
for j in range(0, user_input, 1) :
    print(j + 1)