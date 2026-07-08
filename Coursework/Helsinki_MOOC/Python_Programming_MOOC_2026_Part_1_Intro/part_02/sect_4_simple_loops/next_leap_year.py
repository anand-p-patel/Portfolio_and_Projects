# Write your solution here

user_year = int(input("Year:"))
leap_year = user_year

while True:
    leap_year += 1
    if leap_year % 4 == 0 and leap_year % 100 != 0 or leap_year % 400 == 0:
        print(f"The next leap year after {user_year} is {leap_year}")
        break