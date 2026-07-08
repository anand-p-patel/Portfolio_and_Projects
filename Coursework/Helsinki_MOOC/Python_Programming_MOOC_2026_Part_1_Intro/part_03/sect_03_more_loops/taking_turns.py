# Write your solution here

user_number = int(input("Please type in a number:"))

beginning = 1
end = user_number
while beginning <= end:
    print(beginning)
    beginning += 1
    if beginning <= end:
        print(end)
        end -= 1