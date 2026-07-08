# Write your solution here

#user inputs limit
user_limit = int(input("Limit:"))

#define sum string
consec_sum = ""

#define starting base
start_number = 1
current_sum = 0

while user_limit > current_sum:
    if start_number == 1:
        consec_sum += f"{start_number}"
        current_sum += start_number
        start_number += 1
    else :
        consec_sum += f" + {start_number}"
        current_sum += start_number
        start_number += 1

print(f"The consecutive sum: {consec_sum} = {current_sum}")