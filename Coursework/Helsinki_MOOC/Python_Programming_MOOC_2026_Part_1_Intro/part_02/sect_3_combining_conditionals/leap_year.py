# Write your solution here

#define user input
user_year = int(input("Please type in a year:"))

#checks if divisible by 4
if user_year % 400 == 0:
    print("This is a leap year.")
elif user_year % 100 == 0:
    print("That year is not a leap year.")
elif user_year % 4 == 0:
    print("This is a leap year.")
else:
    print("That year is not a leap year.")