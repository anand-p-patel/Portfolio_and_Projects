# Write your solution here
#write a program that asks a user for words if the user inputs the same word twice program prints  the number of different words the user has inputted and stops the program

word_bank = []
count = 0

while True:
    user_input = str(input("Word: "))
    word_bank.append(user_input)
    if user_input in word_bank[:-1]:
        print(f"You typed in {count} different words")
        break
    count += 1