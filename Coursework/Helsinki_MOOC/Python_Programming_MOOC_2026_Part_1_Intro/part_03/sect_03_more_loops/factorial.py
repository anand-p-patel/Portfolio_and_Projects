# Write your solution here

while True : 
    user_integer = int(input("Please type in a number:"))
    if user_integer <= 0 :
        print("thanks and bye!")
        break
    index = 1
    factorial = 1
    while index <= user_integer :
        factorial *= index
        index += 1
    print(f"The factorial of the number {user_integer} is {factorial}")