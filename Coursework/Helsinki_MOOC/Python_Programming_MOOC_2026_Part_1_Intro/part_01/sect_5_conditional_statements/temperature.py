# Write your solution here
#user input
temperature_fahreneit = int(input("Please type in a temperature(F): "))

cel_conver = (temperature_fahreneit - 32) * (5/9)

print(f"{temperature_fahreneit} degrees Fahrenheit equals {cel_conver} degrees Celsius")

if cel_conver < 0:
    print(f"Brr! It's cold in here!")