# write your solution here

def largest():
    with open("numbers.txt", "r") as file:
        highest_number = max((line.strip() for line in file if line.strip()), key = int)
    return int(highest_number)