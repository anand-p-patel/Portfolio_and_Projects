# Write your solution here

#user inputs limit
user_limit = int(input("Limit:"))

#define starting base
start_number = 1
current_sum = 0

while user_limit > current_sum:
    current_sum += start_number
    start_number += 1
    

print(current_sum)