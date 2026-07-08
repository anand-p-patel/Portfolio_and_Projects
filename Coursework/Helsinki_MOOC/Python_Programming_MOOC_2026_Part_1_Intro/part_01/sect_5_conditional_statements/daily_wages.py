# Write your solution here

#user inputs
hourly_wage = float(input("Hourly wage:"))
hours_worked = int(input("Hours worked: "))
day = input("Day of the week:")

#define arithmetics
daily_wage = hourly_wage * hours_worked
double_daily = 2 * daily_wage

if day != "Sunday":
    print(f"Daily wages: {daily_wage} euros")

#sunday conditional
if day == "Sunday":
    print(f"Daily wages: {double_daily} euros")