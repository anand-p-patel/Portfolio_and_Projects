# Write your solution here

#define user input
user_number = float(input("Please type in a number:"))

#define parts
decimal_number = user_number - int(user_number) 
whole_number = int(user_number)

#print results
print(f"Integer part: {whole_number}")
print(f"Decimal part: {decimal_number}")