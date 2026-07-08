# Write your solution here

user_number = int(input("Please type in a number:"))
outer = 1
while user_number >= outer :
    inner = 1
    while inner <= user_number :
        print(f"{outer} x {inner} = {outer * inner}" )
        inner += 1
    outer += 1