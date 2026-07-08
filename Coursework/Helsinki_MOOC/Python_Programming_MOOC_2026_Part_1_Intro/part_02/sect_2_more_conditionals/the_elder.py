# Write your solution here

#define person 1
print("Person 1:")
name_one = str(input("Name:"))
age_one = int(input("Age:"))

#define person 2
print("Person 2:")
name_two = str(input("Name:"))
age_two = int(input("Age:"))

#conditional age checks
if age_one > age_two:
    print(f"The elder is {name_one}")
elif age_one < age_two:
    print(f"The elder is {name_two}")
else:
    print(f"{name_one} and {name_two} are the same age")