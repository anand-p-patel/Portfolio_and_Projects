# Write your solution here
input_password_original = str(input("Password:"))
input_password_repeat = str(input("Repeat password:"))

while True:
    if input_password_original != input_password_repeat:
        print("They do not match!")
        input_password_repeat = str(input("Repeat password:"))
    if input_password_original == input_password_repeat:
        print("User account created!")
        break