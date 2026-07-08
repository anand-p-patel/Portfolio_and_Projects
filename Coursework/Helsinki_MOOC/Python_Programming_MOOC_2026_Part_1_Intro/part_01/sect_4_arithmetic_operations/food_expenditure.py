# Write your solution here
cafeteria_days = int(input("How many times a week do you eat at the student cafeteria?"))
lunch_price = float(input("The price of a typical student lunch?"))
grocery_spend = float(input("How much money do you spend on groceries in a week?"))

cafeteria_spend = cafeteria_days * lunch_price
weekly_spend = cafeteria_spend + grocery_spend
daily_spend = weekly_spend / 7
print("Average food expenditure:")
print(f"Daily: {daily_spend} euros")
print(f"Weekly: {weekly_spend} euros")