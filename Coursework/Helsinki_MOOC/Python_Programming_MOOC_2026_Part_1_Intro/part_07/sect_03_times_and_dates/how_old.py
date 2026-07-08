# Write your solution here
from datetime import datetime, timedelta

user_day = int(input("Day: "))
user_month = int(input("Month: "))
user_year = int(input("Year: "))
birthday = datetime(user_year, user_month, user_day)
new_millenium = datetime(1999, 12, 31)
age_mil = new_millenium - birthday
if age_mil.days > 0:
    print(f"You were {age_mil.days} days old on the eve of the new millennium.")
elif age_mil.days < 0:
    print("You weren't born yet on the eve of the new millennium.")