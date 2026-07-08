# Write your solution here

#define user inputs
letter_one = str(input("!st letter:"))
letter_two = str(input("2nd letter:"))
letter_three = str(input("3rd_letter"))

middle = False
middle_letter = ""

#check order
if letter_one > letter_two > letter_three:
    middle = True
    middle_letter = letter_two
elif letter_one > letter_three > letter_two:
    middle = True
    middle_letter = letter_three
elif letter_three > letter_two > letter_one:
    middle = True
    middle_letter = letter_two
elif letter_three > letter_one > letter_two:
    middle = True
    middle_letter = letter_one
elif letter_two > letter_one > letter_three:
    middle = True
    middle_letter = letter_one
elif letter_two > letter_three > letter_one:
    middle = True
    middle_letter = letter_three
print(f"The letter in the middle is {middle_letter}")