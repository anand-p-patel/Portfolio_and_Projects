# Write your solution here

user_number = int(input("Please type in a number:"))

index = 2

while index <= user_number :
    print(index)
    if index - 1 <= user_number:
        print(index - 1)
    index += 2
if user_number % 2 != 0:
    print(user_number) 