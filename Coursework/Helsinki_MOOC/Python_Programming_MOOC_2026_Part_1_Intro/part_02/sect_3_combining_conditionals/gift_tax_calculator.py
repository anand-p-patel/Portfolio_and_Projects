# Write your solution here
#define gift value
gift_value = int(input("Value of gift:"))
tax = ""

#check tax brackets
if gift_value < 5000:
    tax = 0
elif gift_value >= 5000 and gift_value <= 25000:
    tax = float((100 + (gift_value - 5000) * 0.08))
elif gift_value >= 25000 and gift_value <= 55000:
    tax = float((1700 + (gift_value - 25000) * .1))
elif gift_value >= 55000 and gift_value <= 200000:
    tax = float((4700 + (gift_value - 55000) * .12))
elif gift_value >= 200000 and gift_value <= 1000000:
    tax = float((22100 + (gift_value - 200000) * .15))
else:
    tax = float(142100 + (gift_value - 1000000 ) * .17)

#print tax
if tax == 0:
    print("No tax!")
else:
    print(f"Amount of tax: {tax} euros")
